"""Load stack definitions from YAML files or built-in presets."""

from __future__ import annotations

import importlib.resources
import logging
from pathlib import Path

import yaml

from mcp_tap.errors import McpTapError
from mcp_tap.models import Stack, StackServer

logger = logging.getLogger(__name__)

# Built-in stack names
BUILTIN_STACKS = {"data-science", "web-dev", "devops"}


def load_stack(name_or_path: str) -> Stack:
    """Load a stack by built-in name or file path.

    Args:
        name_or_path: Either a built-in stack name (e.g. "data-science")
            or a path to a .yaml/.yml file.

    Returns:
        Parsed Stack object.

    Raises:
        McpTapError: If the stack cannot be loaded or parsed.
    """
    path = Path(name_or_path)
    if path.suffix in (".yaml", ".yml") or path.exists():
        return _load_from_file(path)

    if name_or_path in BUILTIN_STACKS:
        return _load_builtin(name_or_path)

    raise McpTapError(
        f"Unknown stack '{name_or_path}'. "
        f"Available built-in stacks: {', '.join(sorted(BUILTIN_STACKS))}. "
        "Or provide a path to a .yaml file."
    )


def list_builtin_stacks() -> list[dict[str, object]]:
    """Return metadata about all built-in stacks."""
    result: list[dict[str, object]] = []
    for name in sorted(BUILTIN_STACKS):
        try:
            stack = _load_builtin(name)
            result.append(
                {
                    "name": stack.name,
                    "description": stack.description,
                    "server_count": len(stack.servers),
                    "author": stack.author,
                }
            )
        except Exception:
            result.append({"name": name, "description": "Failed to load", "server_count": 0})
    return result


def _load_builtin(name: str) -> Stack:
    """Load a built-in stack from package resources."""
    try:
        ref = importlib.resources.files("mcp_tap.stacks") / "presets" / f"{name}.yaml"
        text = ref.read_text(encoding="utf-8")
        return _parse_yaml(text, source=f"builtin:{name}")
    except FileNotFoundError:
        raise McpTapError(f"Built-in stack '{name}' not found.") from None
    except McpTapError:
        raise
    except Exception as exc:
        raise McpTapError(f"Failed to load built-in stack '{name}': {exc}") from exc


def _load_from_file(path: Path) -> Stack:
    """Load a stack from a YAML file on disk."""
    if not path.exists():
        raise McpTapError(f"Stack file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
        return _parse_yaml(text, source=str(path))
    except McpTapError:
        raise
    except Exception as exc:
        raise McpTapError(f"Failed to parse stack file '{path}': {exc}") from exc


def _parse_yaml(text: str, source: str = "") -> Stack:
    """Parse YAML text into a Stack object."""
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise McpTapError(f"Invalid stack format in {source}: expected a YAML mapping.")

    name = data.get("name", "unnamed")
    description = data.get("description", "")
    version = str(data.get("version", "1"))
    author = data.get("author", "")

    servers_data = data.get("servers", [])
    if not isinstance(servers_data, list):
        raise McpTapError(f"Invalid stack format in {source}: 'servers' must be a list.")

    servers: list[StackServer] = []
    for entry in servers_data:
        if not isinstance(entry, dict):
            continue
        servers.append(
            StackServer(
                name=entry.get("name", ""),
                package_identifier=entry.get("package", ""),
                registry_type=entry.get("registry", "npm"),
                version=str(entry.get("version", "latest")),
                env_vars=list(entry.get("env_vars", [])),
            )
        )

    return Stack(
        name=name,
        description=description,
        servers=servers,
        version=version,
        author=author,
    )
