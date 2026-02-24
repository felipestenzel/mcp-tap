"""Smoke test to verify the built package works."""

from importlib.metadata import version as distribution_version

from mcp_tap import __version__, main

assert __version__ == distribution_version("mcp-tap"), f"Version mismatch: got {__version__}"
assert callable(main), "main() entry point must be callable"

print(f"mcp-tap {__version__} smoke test passed")
