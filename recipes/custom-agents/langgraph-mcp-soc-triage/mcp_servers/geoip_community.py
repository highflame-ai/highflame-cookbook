#!/usr/bin/env python3
"""geoip-community MCP server — the deliberate SHADOW server (stdio).

This server is NOT registered in Studio's MCP registry, on purpose. The
Threat Analyst reaches it directly, the calls work, and nothing about them is
governed or recorded — which is exactly the story: coverage is bounded by what
is fronted. In Studio's MCP coverage view (ADR 0018) this server surfaces as
shadow — discovered-or-observed but ungoverned — while soc-logs, threat-intel,
and edge-firewall show as covered.

Do NOT "fix" this by registering it. The gap is the feature.
"""
from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("geoip-community")

GEO = {
    "203.0.113.7": {"country": "ZZ", "city": "Reserved (TEST-NET-3)"},
    "198.51.100.23": {"country": "ZZ", "city": "Reserved (TEST-NET-2)"},
    "198.51.100.80": {"country": "ZZ", "city": "Reserved (TEST-NET-2)"},
    "192.0.2.66": {"country": "ZZ", "city": "Reserved (TEST-NET-1)"},
}


@mcp.tool()
def geoip(ip: str) -> str:
    """Return best-effort geolocation for an IP address (community data, unverified)."""
    return json.dumps({"ip": ip, **GEO.get(ip, {"country": "??", "city": "unknown"})})


if __name__ == "__main__":
    mcp.run()
