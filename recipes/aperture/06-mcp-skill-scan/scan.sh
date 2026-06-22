#!/usr/bin/env bash
# Scan the MCP servers your coding agent can reach for tool poisoning, prompt
# injection, and sensitive-data exposure — BEFORE they touch production work.
#
# Requires the ramparts CLI: https://github.com/highflame-ai/ramparts
set -euo pipefail

if ! command -v ramparts >/dev/null 2>&1; then
  echo "ramparts not installed — see https://github.com/highflame-ai/ramparts" >&2
  exit 2
fi

# 1) Scan your IDE's configured MCP servers (~/.cursor/mcp.json, Claude, Windsurf, …)
ramparts scan-config --format json

# 2) Or scan a single MCP server directly:
# ramparts scan http://localhost:3000 --format table
