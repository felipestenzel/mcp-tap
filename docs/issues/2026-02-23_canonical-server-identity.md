# Identidade canônica de servidor: eliminar falsos-negativos por alias drift

- **Date**: 2026-02-23
- **Status**: `in_progress`
- **Branch**: `feature/2026-02-23-canonical-server-identity`
- **Priority**: `medium`

## Problem

Um servidor MCP instalado pelo usuário pode ter um `name` local (alias) diferente do
`package_identifier` canônico que veio do registry. Hoje, `verify`, `restore`, `scan` e
`list_installed` usam apenas o `name` para identificar servidores, o que gera:

- **`verify`**: reporta `MISSING` + `EXTRA` para o mesmo pacote instalado sob alias diferente
  (ex: lockfile diz `vercel-mcp`, config tem `vercel` — são o mesmo `@vercel/mcp-server`)
- **`restore`**: reinstala um pacote já presente se o `name` no lockfile diverge do alias local
- **`scan`**: `_is_recommendation_installed` faz matching parcial (URL OK, mas `package_identifier`
  em `args` não é comparado com canonical key completa)
- **`list_installed`**: não expõe `package_identifier` nem `repository_url` — usuário não consegue
  ver a provenance do que está instalado
- **`verify` (regressão v0.6.2)**: lockfile HTTP canônico (`command=""`) vs configuração instalada
  via `mcp-remote` gera falso `CONFIG_CHANGED` mesmo quando a URL é idêntica

## Context

### O que JÁ existe (e está correto)

- `LockedServer` (models.py) já persiste `package_identifier`, `registry_type`,
  `repository_url` — o lockfile é a fonte de verdade canônica
- `AggregatedRegistry` já usa `repository_url` (`owner/repo`) como chave de deduplicação
  interna — prova que o conceito de identidade canônica já existe no projeto
- `_is_recommendation_installed` (v0.6.1) já faz matching por URL e por command/args — base
  sobre a qual construir

### O que está faltando

- `InstalledServer` (models.py:131-137) tem apenas `name`, `config`, `source_file`:
  nenhum campo canônico
- `config/reader.py:parse_servers()` retorna `InstalledServer` sem identidade canônica
  (o arquivo de config JSON do cliente MCP não armazena `package_identifier`)
- `lockfile/differ.py:diff_lockfile()` compara por `name` (alias) apenas
- `tools/restore.py` não verifica se o package já existe sob alias diferente antes de instalar
- `tools/list.py` não expõe campos canônicos no output

### Por que o reader não pode extrair a identidade do config JSON

O formato de config dos clientes MCP é:
```json
{"mcpServers": {"vercel": {"command": "npx", "args": ["-y", "mcp-remote", "https://..."]}}}`
```
Não há `package_identifier` ou `registry_type` armazenados — o reader só tem runtime config.
A identidade canônica precisa vir do lockfile (cross-reference) ou ser inferida de `command`/`args`.

## Root Cause

`InstalledServer` não carrega identidade canônica e os subsistemas que comparam servidores
instalados com entradas do lockfile (`differ`, `restore`, `scan`) não têm como fazer matching
além do alias local.

A solução correta é **adicionar campos canônicos a `InstalledServer`** com defaults vazios e
**preencher esses campos via lockfile cross-reference** nos pontos de uso — sem tocar no schema
do arquivo de config do cliente MCP.

Para a regressão específica de `verify` em HTTP, o problema imediato é adicional:
`lockfile/differ.py` comparava apenas `command/args`, sem tratar equivalência semântica entre
configuração nativa HTTP e configuração `mcp-remote` com a mesma URL.

## Solution

### Update 2026-02-23 — correção aplicada (sem issue separada)

Conforme decisão desta sessão, **não foi aberta issue separada** para a regressão de `verify`.
A correção foi implementada nesta mesma trilha por alta sobreposição de código em `differ.py`.

Implementado:
- `lockfile/differ.py` agora detecta entradas HTTP no lockfile e compara por **URL canônica**
  (não por `command/args`)
- Equivalência aceita:
  - lockfile HTTP + instalado nativo `HttpServerConfig(url=...)`
  - lockfile HTTP + instalado `mcp-remote ... <url>`
- Mismatch real continua sendo detectado:
  - URLs diferentes => `CONFIG_CHANGED`
- Casos não-HTTP continuam com comparação estrita de `command/args` (sem regressão)

Cobertura de regressão adicionada em `tests/test_differ.py`, incluindo cenário com
`command=""` e `args=[]` no lockfile.

### Abordagem recomendada em 3 camadas

**Camada 1 — Modelo** (`models.py`):

Adicionar 3 campos com default `""` a `InstalledServer`:
```python
@dataclass(frozen=True, slots=True)
class InstalledServer:
    name: str
    config: ServerConfig | HttpServerConfig
    source_file: str
    package_identifier: str = ""   # ex: "@mcp/server-postgres", "https://mcp.vercel.com"
    registry_type: str = ""        # ex: "npm", "pypi", "streamable-http"
    repository_url: str = ""       # ex: "https://github.com/modelcontextprotocol/servers"
```

Backward-compatible: todo código existente que cria `InstalledServer` sem os novos campos
continuará funcionando (default `""`).

**Camada 2 — Cross-reference com lockfile** (`lockfile/differ.py`, `tools/restore.py`):

Nesses dois módulos já se tem acesso ao lockfile. Usar `LockedServer.package_identifier` como
chave secundária de busca no `installed`:

```python
# Em differ.py
def _find_installed(name: str, locked: LockedServer, installed: list[InstalledServer]):
    # 1. Match por nome (rápido, mantém comportamento existente)
    by_name = {s.name: s for s in installed}
    if name in by_name:
        return by_name[name]
    # 2. Match por identidade canônica (evita falso-negativo por alias)
    for s in installed:
        if s.package_identifier and s.package_identifier == locked.package_identifier:
            return s
    # 3. Match por URL/args heurístico (servidores sem package_identifier no InstalledServer)
    for s in installed:
        if _config_matches_package_id(s.config, locked.package_identifier):
            return s
    return None
```

Adicionar função auxiliar `_config_matches_package_id(config, pkg_id)` que:
- Para `HttpServerConfig`: compara `url == pkg_id`
- Para `ServerConfig`: verifica se `pkg_id in args` (detecta `npx -y @pkg/name`)

**Camada 3 — Enriquecimento no scan e list** (`tools/scan.py`, `tools/list.py`):

- `scan`: `_is_recommendation_installed` já usa a lógica de matching — pode ser simplificada
  para delegar para a mesma função `_config_matches_package_id` de differ.py
  (evita duplicação de lógica entre scan.py e differ.py — refatorar para módulo compartilhado
  em `mcp_tap.config.matching` ou similar)
- `list_installed`: quando `InstalledServer.package_identifier != ""`, incluir no output

### O que NÃO fazer

- **Não armazenar campos canônicos no config JSON do cliente MCP**: seria invasivo, quebraria
  configs editadas manualmente, e os clientes MCP poderiam ignorar/rejeitar campos extras
- **Não adicionar smithery_id a InstalledServer**: escopo desnecessário para esta issue; o
  aggregator já resolve deduplicação Smithery internamente
- **Não bloquear `restore` se a identidade não puder ser confirmada**: se `package_identifier`
  está vazio (servidor instalado manualmente), fallback para comportamento existente (instala)

## Files Changed

- `src/mcp_tap/lockfile/differ.py` — equivalência HTTP por URL para eliminar falso `CONFIG_CHANGED`
- `tests/test_differ.py` — regressões HTTP (native vs mcp-remote, URL mismatch, lockfile args vazio)
- `docs/issues/2026-02-23_canonical-server-identity.md` — decisão de escopo e progresso

## Verification

- [x] Tests pass: `pytest tests/` (1238 passed)
- [x] Linter passes: `ruff check src/ tests/ && ruff format --check src/ tests/`
- [x] `verify`: lockfile HTTP + `mcp-remote` com mesma URL → sem `CONFIG_CHANGED`
- [x] `verify`: lockfile HTTP + config nativa HTTP com mesma URL → sem `CONFIG_CHANGED`
- [x] `verify`: lockfile HTTP + URL instalada diferente → `CONFIG_CHANGED`
- [ ] `verify`: lockfile com alias diferente (não-HTTP) + mesma canonical key → sem `MISSING/EXTRA`
- [ ] `restore`: package já instalado como `vercel` → `status: already_installed`, sem reinstall
- [ ] `list_installed`: servidores com `package_identifier` populado mostram o campo
- [ ] Servidores instalados manualmente (sem mcp-tap) → comportamento idêntico ao atual

## Edge Cases

| Caso | Comportamento esperado |
|------|------------------------|
| Servidor instalado manualmente sem mcp-tap | `package_identifier=""`, fallback para matching por nome — sem regressão |
| HTTP (`HttpServerConfig`) com alias diferente | Matching via `url == package_identifier` |
| Stdio com alias diferente | Matching via `pkg_id in args` (ex: `npx -y @pkg/name`) |
| Lockfile de versão anterior (sem campos novos) | Backward-compat: campos default `""` — sem impacto |
| Config file sem entrada no lockfile | `InstalledServer.package_identifier=""` — tratado como não-canônico |

## Lessons Learned

(Optional)
