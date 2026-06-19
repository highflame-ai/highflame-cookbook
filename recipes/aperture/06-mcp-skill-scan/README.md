# 06 · MCP scan & SKILL scan (pre-runtime supply-chain)

**Customer value:** *"Before our developers connect an MCP server or install an agent skill,
we want to know it isn't poisoned — tool shadowing, hidden prompt injection, a tool that
quietly exfiltrates secrets."*

Unlike recipes 01–05 (request-time, via the Aperture hook), this is **pre-runtime**: you scan
what a developer is about to plug in. Two surfaces:

| Surface | Tool | Catches |
| --- | --- | --- |
| **MCP scan** | [`ramparts`](https://github.com/highflame-ai/highflame-ramparts) CLI | tool poisoning, tool shadowing, prompt injection, SQL injection, auth bypass, sensitive-data / PII exposure in an MCP server's tools & resources |
| **SKILL scan** | Overwatch / Guardian (native IDE hook) | malicious or risky Claude Code **skills**, surfaced as `skill_finding` events |

Both feed **Studio → Code Agents**, so security teams get an inventory and findings across the org.

---

## MCP scan — `ramparts`

```bash
# Scan the MCP servers your coding agent is configured to reach
# (~/.cursor/mcp.json, Claude, Windsurf, …):
ramparts scan-config --format json

# Or scan a single MCP server directly:
ramparts scan http://localhost:3000 --format table
```

See [`scan.sh`](scan.sh) for the runnable version. ramparts checks each tool/resource the
server exposes against its security rule set (YARA-X + LLM analysis) and reports findings
per server.

---

## SKILL scan — Overwatch

The Overwatch agent (the same native-hook install that powers Claude Code enforcement) scans
the **skills** configured in a developer's IDE and emits `skill_finding` telemetry. Findings
appear in **Studio → Code Agents** alongside MCP scans and command analysis — no separate
tool to run.

---

## Verify

```bash
python smoke_test.py
```

Confirms the `ramparts` CLI is installed and invokable (a full scan needs a live MCP server
or your IDE's configured servers, so CI verifies the tool rather than a fixed target). Skips
cleanly if ramparts isn't installed.

---

## Notes & honesty

- **Install ramparts** from [highflame-ramparts](https://github.com/highflame-ai/highflame-ramparts)
  (it's a Rust CLI). The smoke test skips if it's not on `PATH`.
- **This is the supply-chain layer**, complementary to the request-time recipes: scan *before*
  you connect (here), enforce *at request time* (01–05).
- Studio shows MCP-scan and skill-scan results under **Code Agents** for org-wide visibility.
