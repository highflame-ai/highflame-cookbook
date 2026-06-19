# 06 · MCP scan & SKILL scan (pre-runtime)

**The value:** *"Before our developers connect an MCP server or install an agent skill, we
want to know it isn't poisoned — tool shadowing, hidden prompt injection, a tool that
quietly exfiltrates secrets."*

Unlike recipes 01–05 (which act at request time), this one runs *before* anything is used —
you scan what a developer is about to plug in. Two surfaces:

| Surface | How | Catches |
| --- | --- | --- |
| **MCP scan** | the [`ramparts`](https://github.com/highflame-ai/highflame-ramparts) CLI | tool poisoning, tool shadowing, prompt injection, SQL injection, auth bypass, sensitive-data / PII exposure in an MCP server's tools and resources |
| **SKILL scan** | Highflame's native IDE integration | malicious or risky agent **skills**, reported as findings |

Both feed **Studio → Code Agents**, so security teams get an org-wide inventory and findings.

---

## MCP scan — `ramparts`

```bash
# Scan the MCP servers your coding agent is configured to reach
# (~/.cursor/mcp.json, Claude, Windsurf, …):
ramparts scan-config --format json

# Or scan a single MCP server directly:
ramparts scan http://localhost:3000 --format table
```

See [`scan.sh`](scan.sh) for the runnable version. `ramparts` checks each tool and resource a
server exposes against its security rule set and reports findings per server.

---

## SKILL scan

Highflame's native IDE integration (the same install that powers request-time enforcement)
scans the **skills** configured in a developer's IDE and reports risky ones. Findings appear
in **Studio → Code Agents** alongside MCP scans — no separate tool to run.

---

## Verify

```bash
python smoke_test.py
```

Confirms the `ramparts` CLI is installed and callable. (A full scan runs against a live MCP
server or your IDE's configured servers; the check skips if `ramparts` isn't installed.)

---

## Notes

- **Install ramparts** from [highflame-ramparts](https://github.com/highflame-ai/highflame-ramparts).
- **This is the supply-chain layer**, complementary to the request-time recipes: scan
  *before* you connect (here), enforce *at request time* (01–05).
- Results appear in Studio → Code Agents for org-wide visibility.
