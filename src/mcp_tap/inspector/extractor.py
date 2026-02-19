"""Extract configuration hints from server README markdown text."""

from __future__ import annotations

import re

from mcp_tap.models import ConfigHints, EnvVarHint

# ─── Regex patterns ──────────────────────────────────────────

_CODE_BLOCK_RE = re.compile(r"```[a-z]*\n(.*?)```", re.DOTALL)

_ENV_VAR_RE = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\b")

_INSTALL_CMD_RE = re.compile(
    r"(?:npm\s+install|npx\s+-y|pip\s+install|uvx|docker\s+run|docker\s+pull)"
    r"[^\n]*",
    re.IGNORECASE,
)

_TRANSPORT_RE = re.compile(
    r"\b(stdio|streamable-http|sse)\b",
    re.IGNORECASE,
)

_SERVER_CMD_RE = re.compile(
    r"(?:npx\s+-y|uvx|python\s+-m|node\s+)[^\n]+",
    re.IGNORECASE,
)

# JSON config blocks that look like MCP config
_JSON_CONFIG_RE = re.compile(
    r'\{[^}]*"command"[^}]*\}',
    re.DOTALL,
)

# Words that suggest an env var is required
_REQUIRED_KEYWORDS = re.compile(
    r"\b(required|must|need|set|export|mandatory)\b",
    re.IGNORECASE,
)

# Common non-env-var uppercase words to filter out
_IGNORE_VARS = frozenset(
    {
        "README",
        "MCP",
        "API",
        "URL",
        "JSON",
        "HTTP",
        "HTTPS",
        "SSH",
        "GET",
        "POST",
        "PUT",
        "DELETE",
        "HEAD",
        "OPTIONS",
        "PATCH",
        "TRUE",
        "FALSE",
        "NULL",
        "ENV",
        "VAR",
        "CLI",
        "SDK",
        "NPM",
        "NPX",
        "PIP",
        "UVX",
        "DOCKER",
        "GIT",
        "SQL",
        "MIT",
        "BSD",
        "ISC",
        "AGPL",
        "GPL",
        "LGPL",
        "TODO",
        "NOTE",
        "WARNING",
        "TIP",
        "IMPORTANT",
        "SSE",
        "STDIO",
        "TCP",
        "UDP",
    }
)


def _extract_code_blocks(readme: str) -> list[str]:
    """Extract all fenced code blocks from markdown."""
    return _CODE_BLOCK_RE.findall(readme)


def _extract_env_vars(readme: str, code_blocks: list[str]) -> list[EnvVarHint]:
    """Extract environment variable mentions from README."""
    seen: set[str] = set()
    hints: list[EnvVarHint] = []

    # Prioritize env vars in code blocks
    for block in code_blocks:
        for match in _ENV_VAR_RE.finditer(block):
            name = match.group(1)
            if name in seen or name in _IGNORE_VARS or len(name) < 4:
                continue
            # Must look like an env var (has underscore or ends with KEY/TOKEN/URL/SECRET)
            if "_" not in name:
                continue
            seen.add(name)
            # Get surrounding context (the line containing the var)
            line_start = block.rfind("\n", 0, match.start()) + 1
            line_end = block.find("\n", match.end())
            if line_end == -1:
                line_end = len(block)
            context = block[line_start:line_end].strip()
            is_required = bool(_REQUIRED_KEYWORDS.search(context))
            hints.append(EnvVarHint(name=name, context=context, is_required=is_required))

    # Also scan full text for env vars near keywords like "environment" or "env"
    for line in readme.split("\n"):
        if not any(kw in line.lower() for kw in ("env", "environment", "variable", "token", "key")):
            continue
        for match in _ENV_VAR_RE.finditer(line):
            name = match.group(1)
            if name in seen or name in _IGNORE_VARS or len(name) < 4 or "_" not in name:
                continue
            seen.add(name)
            is_required = bool(_REQUIRED_KEYWORDS.search(line))
            hints.append(EnvVarHint(name=name, context=line.strip(), is_required=is_required))

    return hints


def _extract_install_commands(code_blocks: list[str]) -> list[str]:
    """Extract install/run commands from code blocks."""
    commands: list[str] = []
    for block in code_blocks:
        for match in _INSTALL_CMD_RE.finditer(block):
            cmd = match.group(0).strip()
            if cmd and cmd not in commands:
                commands.append(cmd)
    return commands


def _extract_transport_hints(readme: str) -> list[str]:
    """Extract transport type hints from the full README."""
    found: set[str] = set()
    for match in _TRANSPORT_RE.finditer(readme):
        found.add(match.group(1).lower())
    return sorted(found)


def _extract_command_patterns(code_blocks: list[str]) -> list[str]:
    """Extract server invocation command patterns from code blocks."""
    patterns: list[str] = []
    for block in code_blocks:
        for match in _SERVER_CMD_RE.finditer(block):
            cmd = match.group(0).strip()
            if cmd and cmd not in patterns:
                patterns.append(cmd)
    return patterns


def _extract_json_configs(code_blocks: list[str]) -> list[str]:
    """Extract JSON config blocks that look like MCP server config."""
    configs: list[str] = []
    for block in code_blocks:
        for match in _JSON_CONFIG_RE.finditer(block):
            raw = match.group(0).strip()
            if raw and raw not in configs:
                configs.append(raw)
    return configs


def extract_config_hints(readme: str) -> ConfigHints:
    """Extract structured configuration hints from a README markdown text.

    Uses regex-based pattern matching (no LLM calls). The extracted hints
    are meant to supplement registry data and help the LLM reason about
    server configuration.

    Args:
        readme: Raw markdown text of the server's README.

    Returns:
        ConfigHints with extracted data and a confidence score.
    """
    code_blocks = _extract_code_blocks(readme)
    env_vars = _extract_env_vars(readme, code_blocks)
    install_commands = _extract_install_commands(code_blocks)
    transport_hints = _extract_transport_hints(readme)
    command_patterns = _extract_command_patterns(code_blocks)
    json_configs = _extract_json_configs(code_blocks)

    # Compute confidence based on how many patterns matched
    signals = sum(
        [
            len(install_commands) > 0,
            len(env_vars) > 0,
            len(transport_hints) > 0,
            len(command_patterns) > 0,
            len(json_configs) > 0,
        ]
    )
    confidence = min(signals / 4.0, 1.0)

    return ConfigHints(
        install_commands=install_commands,
        transport_hints=transport_hints,
        env_vars_mentioned=env_vars,
        command_patterns=command_patterns,
        json_config_blocks=json_configs,
        confidence=confidence,
    )
