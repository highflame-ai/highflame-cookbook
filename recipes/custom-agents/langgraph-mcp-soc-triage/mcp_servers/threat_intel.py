#!/usr/bin/env python3
"""threat-intel MCP server — IP reputation and ASN lookup (stdio).

Static reputation data seeded so exactly one indicator confirms as C2: the
beacon destination 203.0.113.7 scores 0.92 with a known-C2 tag. Everything
else the Collector surfaces comes back clean, so the Threat Analyst's verdict
rests on two independent signals (beacon regularity + reputation), not one.

FRONTED: registered in Studio's MCP registry, like soc_logs.py.
"""
from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("threat-intel")

REPUTATION = {
    "203.0.113.7": {
        "score": 0.92,
        "tags": ["c2", "cobaltstrike-watchlist"],
        "first_seen": "34 days ago",
        "note": "Beaconing C2 endpoint reported by two exchange partners.",
    },
    "198.51.100.23": {"score": 0.03, "tags": ["saas"], "first_seen": "3 years ago", "note": "Known SaaS vendor."},
    "198.51.100.80": {"score": 0.05, "tags": ["saas"], "first_seen": "2 years ago", "note": "Known SaaS vendor."},
    "192.0.2.66": {"score": 0.01, "tags": ["cdn"], "first_seen": "5 years ago", "note": "Artifact CDN."},
}

ASN = {
    "203.0.113.7": {"asn": "AS64511", "org": "DOCNET-RESERVED", "rank_by_traffic": "rare"},
    "198.51.100.23": {"asn": "AS64500", "org": "SAAS-VENDOR-NET", "rank_by_traffic": "top-100"},
    "198.51.100.80": {"asn": "AS64500", "org": "SAAS-VENDOR-NET", "rank_by_traffic": "top-100"},
    "192.0.2.66": {"asn": "AS64501", "org": "CDN-EXAMPLE", "rank_by_traffic": "top-10"},
}


@mcp.tool()
def ip_reputation(ip: str) -> str:
    """Return the reputation record for an IP address (score 0..1, higher is worse)."""
    rec = REPUTATION.get(ip)
    if not rec:
        return json.dumps({"ip": ip, "score": 0.0, "tags": [], "note": "No record."})
    return json.dumps({"ip": ip, **rec}, indent=2)


@mcp.tool()
def asn_lookup(ip: str) -> str:
    """Return the ASN and org that announce an IP address."""
    rec = ASN.get(ip)
    if not rec:
        return json.dumps({"ip": ip, "asn": "unknown"})
    return json.dumps({"ip": ip, **rec}, indent=2)


if __name__ == "__main__":
    mcp.run()
