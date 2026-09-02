#!/usr/bin/env python3
"""edge-firewall MCP server — the one destructive capability in the demo (stdio).

`block_ip` is the action the whole recipe is built around. The server itself
just executes — it holds no approval logic, and that is the point: the
suspend-pending-approval behaviour lives entirely in policy. A Cedar policy
carrying `@step_up_required("soc_lead")` (see policies/step-up-block-ip.cedar)
makes Shield return `decision: step_up` on the guarded tool call, and the CIBA
approval dance runs in the SDK layer (stepup.py) before this code is reached.

If you see a block land WITHOUT an approval in Studio, the step-up policy is
not active for this tenant — the run prints a warning for exactly that case.

FRONTED: registered in Studio's MCP registry.
"""
from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("edge-firewall")

# In-memory rule table; reset every run. The demo asserts on this via list_rules.
_RULES: list[dict] = []


@mcp.tool()
def block_ip(ip: str, reason: str) -> str:
    """Add a deny rule for an IP at the edge firewall. Destructive; policy-gated upstream."""
    rule = {"id": f"rule-{len(_RULES) + 1}", "action": "deny", "ip": ip, "reason": reason}
    _RULES.append(rule)
    return json.dumps({"applied": True, **rule})


@mcp.tool()
def list_rules() -> str:
    """List the deny rules applied during this run."""
    return json.dumps(_RULES, indent=2)


if __name__ == "__main__":
    mcp.run()
