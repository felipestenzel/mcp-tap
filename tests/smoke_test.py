"""Smoke test to verify the built package works."""

from mcp_tap import __version__, main

assert __version__ == "0.1.0", f"Expected 0.1.0, got {__version__}"
assert callable(main), "main() entry point must be callable"

print(f"mcp-tap {__version__} smoke test passed")
