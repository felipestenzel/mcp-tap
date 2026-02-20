#!/usr/bin/env node

/**
 * mcp-tap npm wrapper — thin shim that delegates to the Python package via uvx.
 *
 * This allows `npx mcp-tap` to work for users who expect npm-style MCP servers.
 * The actual implementation lives in the Python package (PyPI: mcp-tap).
 *
 * Resolution order:
 *   1. uvx (preferred — uv's tool runner, fast and isolated)
 *   2. pipx run (fallback — common Python tool runner)
 *   3. python -m mcp_tap (last resort — requires prior pip install)
 */

"use strict";

const { spawn, execFileSync } = require("child_process");

function commandExists(cmd) {
  try {
    execFileSync(process.platform === "win32" ? "where" : "which", [cmd], {
      stdio: "ignore",
    });
    return true;
  } catch {
    return false;
  }
}

function run(command, args) {
  const child = spawn(command, args, {
    stdio: "inherit",
    shell: false,
  });

  child.on("error", (err) => {
    process.stderr.write(
      `mcp-tap: failed to start '${command}': ${err.message}\n`
    );
    process.exit(1);
  });

  child.on("close", (code) => {
    process.exit(code ?? 1);
  });
}

// Forward all CLI args after the script name
const userArgs = process.argv.slice(2);

if (commandExists("uvx")) {
  run("uvx", ["mcp-tap", ...userArgs]);
} else if (commandExists("pipx")) {
  run("pipx", ["run", "mcp-tap", ...userArgs]);
} else if (commandExists("python3")) {
  run("python3", ["-m", "mcp_tap", ...userArgs]);
} else if (commandExists("python")) {
  run("python", ["-m", "mcp_tap", ...userArgs]);
} else {
  process.stderr.write(
    "mcp-tap: Python runtime not found.\n" +
      "\n" +
      "mcp-tap requires Python 3.11+ to run. Install one of:\n" +
      "  - uv (recommended): https://docs.astral.sh/uv/getting-started/installation/\n" +
      "  - pipx: https://pipx.pypa.io/stable/installation/\n" +
      "  - Python: https://www.python.org/downloads/\n"
  );
  process.exit(1);
}
