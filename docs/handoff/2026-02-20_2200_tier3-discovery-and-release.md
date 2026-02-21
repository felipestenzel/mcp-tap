# Handoff — Tier 3 LLM-guided discovery + release v0.4.2

- **Date**: 2026-02-20 22:00
- **Context consumed**: ~90%

---

## O que foi feito nessa sessão

### 1. Diagnóstico a partir de teste real (scan do próprio mcp-tap)

Um teste real revelou dois problemas distintos:

**Problema A — Scan quality**: Para projetos Python simples (como o próprio mcp-tap), o scan
retornava 0 recomendações e 0 `suggested_searches` úteis porque nenhum dos 6 archetypes
cobria "Python library/CLI tool". O agente ficava sem sinal e improvisava 16+ buscas manuais.

**Problema B — LLM framing**: As instruções não diziam ao LLM como narrar o workflow. Ele
narrava "o scan não gerou recomendações, deixa eu buscar manualmente" — fazendo o produto
parecer quebrado.

**Insight adicional (product-strategy-advisor)**: ~83% das `extra_queries` dos archetypes
existentes retornavam ZERO resultados no registry porque eram queries abstratas
(`monitoring`, `authentication`, `deployment`) e não nomes de serviços específicos.

### 2. PR #43 — Merged ✅

**Branch**: `fix/2026-02-20-scan-quality-llm-framing`
**Testes**: 1092 → 1098 (+6)

Mudanças:
- `scanner/archetypes.py`: Novo archetype `python_library` (Python + build backend + pytest)
- `tools/scan.py`: `_build_summary` diferencia "zero recs com suggested_searches" de "zero
  recs sem nada". `self_check` fortalecido com instrução de framing.
- `server.py`: Seção "Narrative guidance" adicionada.

### 3. Issue estratégica criada

`docs/issues/2026-02-20_tier3-llm-guided-discovery.md` — Documenta o insight central:
> Python vence em parsing. LLMs vencem em raciocinar sobre necessidades.
> A solução é dar ao LLM inputs ricos (project_context) e instruções explícitas (Tier 3),
> não fazer Python tentar raciocinar via archetypes com queries abstratas.

### 4. PR #44 — Aberto, aguarda merge

**Branch**: `feature/2026-02-20-tier3-llm-discovery`
**PR**: https://github.com/felipestenzel/mcp-tap/pull/44
**Testes**: 1098 → 1108 (+10)
**Linter**: limpo

Mudanças:
- `scanner/archetypes.py`: Todas as queries abstratas removidas. Substituídas por nomes
  específicos validados (`vercel`, `sendgrid`, `datadog`, `grafana`, `shopify`). Archetypes
  sem queries validadas ficam com `[]` e o LLM cobre via Tier 3.
- `tools/scan.py`: Campo `project_context` adicionado ao output. Informa ao LLM:
  `inferred_type`, `distribution`, `ci_platform`, `databases`, `services`, `frameworks`.
  `self_check` redesenhado como protocolo de 3 passos.
- `server.py`: Seção "Three-tier discovery architecture" explica o que o Python faz (Tier 1+2)
  vs o que é responsabilidade do LLM (Tier 3).
- `scanner/detector.py`: Detecção de Figma (`FIGMA_*` env, `@figma/` prefix, `figma-js` dep),
  Jira (`JIRA_*`), Confluence (`CONFLUENCE_*`).
- `scanner/recommendations.py`: 3 novos entries no `TECHNOLOGY_SERVER_MAP`:
  - `figma` → `figma-developer-mcp` (npm, HIGH priority, requer `FIGMA_API_KEY`)
  - `jira` → `@atlassian-dc-mcp/jira` (npm, medium)
  - `confluence` → `@atlassian-dc-mcp/confluence` (npm, medium)
- `scanner/credentials.py`: Credential mappings + help URLs para Figma, Jira, Confluence.
- `scanner/hints.py`: ENV_SEARCH_HINTS para `FIGMA_*`, `JIRA_*`, `CONFLUENCE_*`.

---

## O que fazer na próxima sessão

### Passo 1 — Merge PR #44

```bash
gh pr merge 44 --squash --delete-branch
git checkout main && git pull
```

### Passo 2 — Limpeza menor em _build_project_context

Em `tools/scan.py`, a função `_build_project_context` tem `isinstance(t, dict)` checks
que são código morto — os tipos são sempre `DetectedTechnology` dataclasses na call site.

```python
# Linha atual (~216):
tech_names = {
    t["name"].lower() if isinstance(t, dict) else t.name.lower() for t in technologies
}

# Simplificar para:
tech_names = {t.name.lower() for t in technologies}

# E no loop de bucketing (~245):
# Remover o isinstance e usar sempre t.category.value, t.name
```

Isso é cosmético mas deve ser corrigido antes do release.

### Passo 3 — Bump versão e release

```bash
# Editar pyproject.toml: version = "0.4.2"
# Editar npm-wrapper/package.json: "version": "0.4.2"
git add pyproject.toml npm-wrapper/package.json
git commit -m "Bump version to 0.4.2"
git push
gh release create v0.4.2 --title "v0.4.2 — Tier 3 LLM-guided discovery" --notes "..."
```

Após o release verificar:
```bash
pip index versions mcp-tap   # confirmar PyPI
npm view mcp-tap version     # confirmar npm
```

### Passo 4 — Limpar handoffs antigos

```bash
rm docs/handoff/2026-02-19_2400_lockfile-complete-all-merged.md
rm docs/handoff/2026-02-20_0230_hardening-r2-security-stacks.md
rm docs/handoff/2026-02-20_1720_dynamic-discovery-engine.md
# Este arquivo (2026-02-20_2200) também pode ser deletado depois do merge
```

### Passo 5 — Atualizar MEMORY.md

Adicionar às Lessons Learned:
```
- **Python wins at parsing, LLMs win at reasoning about needs**: Archetypes with abstract
  category queries (monitoring, authentication) return ~0 registry results. The right
  Tier 3 approach is to give the LLM a rich project_context and explicit instructions
  to search for specific service names, not categories.
- **Always validate extra_queries against the live registry before adding**: If the query
  returns zero results, do not add it. Only specific service names (proper nouns) work.
- **package_identifiers confirmed for new servers** (via mcp-tap search_servers):
  - figma: figma-developer-mcp (npm, stdio)
  - jira: @atlassian-dc-mcp/jira (npm, stdio)
  - confluence: @atlassian-dc-mcp/confluence (npm, stdio)
  - vercel: https://mcp.vercel.com (streamable-http, not in TECHNOLOGY_SERVER_MAP)
  - sanity: https://mcp.sanity.io (streamable-http, not in TECHNOLOGY_SERVER_MAP)
```

### Passo 6 — Teste real da nova versão

Após instalar v0.4.2 (`uvx mcp-tap@0.4.2`), testar num projeto real:
1. `scan_project` no próprio mcp-tap → deve retornar `project_context` com `python_library`
2. O agente deve usar o `project_context.inferred_type` e fazer buscas como `linear`,
   `notifications`, sem precisar ser guiado manualmente
3. Confirmar que `suggested_searches` não está vazio

---

## Estado atual dos arquivos modificados

### Modificados (não commitados no main — estão na branch)
- `src/mcp_tap/scanner/archetypes.py`
- `src/mcp_tap/scanner/detector.py`
- `src/mcp_tap/scanner/recommendations.py`
- `src/mcp_tap/scanner/credentials.py`
- `src/mcp_tap/scanner/hints.py`
- `src/mcp_tap/tools/scan.py`
- `src/mcp_tap/server.py`
- `tests/test_tools_scan.py`
- `tests/test_discovery_engine.py`

### Versão atual no main
- `v0.4.1` (pyproject.toml + npm-wrapper/package.json)
- 1098 testes passando

### Versão na branch (PR #44)
- `v0.4.1` (bump ainda não feito — fazer no passo 2)
- 1108 testes passando

---

## Decisões tomadas que a próxima sessão deve conhecer

1. **Vercel, Sanity, Shopify NÃO estão no TECHNOLOGY_SERVER_MAP**: Os servidores disponíveis
   são streamable-http com URL como package_identifier. O sistema de install do mcp-tap
   só suporta npm/pip/docker. Esses servidores ficam no Tier 3 (LLM descobre via search).

2. **Archetypes com `extra_queries: []` é correto e intencional**: Não é um bug. O LLM
   faz o Tier 3 com instruções explícitas. Adicionar queries abstratas seria regredir.

3. **O isinstance check em _build_project_context é código morto**: A função sempre recebe
   `DetectedTechnology` objetos, nunca dicts. Pode ser simplificado sem risco.

---

## Roadmap atualizado

| Feature | Status |
|---------|--------|
| Tier 3 LLM-guided discovery | PR #44 aberto |
| v0.4.2 release | Pendente (próxima sessão) |
| Teste real v0.4.2 | Pendente |
| D1 Demo GIF | Pendente (baixa prioridade mas alta visibilidade) |
| D3-D4 Distribuição (HN, docs) | Pendente |
