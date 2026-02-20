"""Port: Stack loading and listing."""

from __future__ import annotations

from typing import Protocol

from mcp_tap.models import Stack


class StackLoaderPort(Protocol):
    """Port for loading stack definitions from YAML or built-in presets."""

    def load_stack(self, name_or_path: str) -> Stack:
        """Load a stack by built-in name or file path."""
        ...

    def list_builtin_stacks(self) -> list[dict[str, object]]:
        """List metadata about all built-in stacks."""
        ...
