"""Compute hashes for lockfile integrity checking."""

from __future__ import annotations

import hashlib


def compute_tools_hash(tools: list[str]) -> str | None:
    """Compute SHA-256 hash of sorted, pipe-joined tool names.

    Returns None if tools list is empty.
    """
    if not tools:
        return None
    joined = "|".join(sorted(tools))
    digest = hashlib.sha256(joined.encode()).hexdigest()
    return f"sha256-{digest}"
