#!/usr/bin/env python3
"""soc-logs MCP server — flow, DNS, and auth logs for the triage demo (stdio).

Seeded with one suspicious pattern the agents must find: workstation
ws-114.corp.example beacons to 203.0.113.7 every ~60s with small, uniform
payloads, alongside ordinary traffic that should not trip anything.

Two deliberate properties of the seed data:

  * The beacon hides in volume. Sorted by bytes or by count, normal SaaS and
    CDN traffic dominates; the beacon only stands out on inter-arrival
    regularity — which is what the Threat Analyst is asked to reason about.
  * The auth log carries employee emails. That is the `modify` beat: a PII
    policy in modify mode redacts them in the tool RESULT at HTTP 200, so the
    triage proceeds on redacted data instead of being blocked.

All addresses are documentation-reserved (203.0.113.0/24, 198.51.100.0/24,
192.0.2.0/24). Every timestamp is a fixed offset from the run's T0 so runs are
deterministic.

This server is FRONTED: registered in Studio's MCP registry, so its traffic is
governed and it counts as covered in the MCP coverage view. Contrast with
geoip_community.py, which is deliberately left unregistered (shadow).
"""
from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("soc-logs")

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

# (src, dst, dst_port, bytes_out, count_last_hour, inter_arrival_stddev_s)
# The beacon row is the only one with near-zero inter-arrival jitter.
FLOWS = [
    ("ws-114.corp.example", "203.0.113.7",   443, 62_400,   60,  0.4),   # beacon
    ("ws-114.corp.example", "198.51.100.23", 443, 8_113_220, 214, 41.7), # SaaS sync
    ("ws-207.corp.example", "198.51.100.23", 443, 6_402_118, 183, 39.2),
    ("ws-207.corp.example", "198.51.100.80", 443, 912_055,   37,  22.9),
    ("build-04.corp.example", "192.0.2.66",  443, 48_119_003, 402, 12.5), # artifact pulls
    ("ws-114.corp.example", "198.51.100.80", 443, 227_930,   12,  60.1),
]

DNS = [
    ("ws-114.corp.example", "cdn-sync-status.example.net", "203.0.113.7", 61),  # rare, beacon C2
    ("ws-114.corp.example", "app.saas-vendor.example",     "198.51.100.23", 214),
    ("ws-207.corp.example", "app.saas-vendor.example",     "198.51.100.23", 183),
    ("build-04.corp.example", "artifacts.example",         "192.0.2.66", 402),
]

# The PII the modify-mode policy redacts. Kept out of FLOWS/DNS on purpose so
# the redaction lands on exactly one tool result and is easy to point at.
AUTH_EVENTS = [
    ("T-58m", "ws-114.corp.example", "dana.reyes@corp.example",  "interactive logon", "ok"),
    ("T-51m", "ws-114.corp.example", "dana.reyes@corp.example",  "token refresh",     "ok"),
    ("T-49m", "ws-114.corp.example", "svc-backup@corp.example",  "service logon",     "ok"),
    ("T-12m", "ws-207.corp.example", "kim.osei@corp.example",    "interactive logon", "ok"),
]


@mcp.tool()
def query_flows(host: str = "") -> str:
    """Return the last hour of egress flow summaries, optionally filtered by source host."""
    rows = [f for f in FLOWS if not host or f[0] == host]
    return json.dumps(
        [
            {
                "src": s, "dst": d, "dst_port": p, "bytes_out": b,
                "count_last_hour": c, "inter_arrival_stddev_s": j,
            }
            for s, d, p, b, c, j in rows
        ],
        indent=2,
    )


@mcp.tool()
def query_dns(host: str = "") -> str:
    """Return the last hour of DNS resolutions, optionally filtered by client host."""
    rows = [r for r in DNS if not host or r[0] == host]
    return json.dumps(
        [
            {"client": c, "qname": q, "answer": a, "count_last_hour": n}
            for c, q, a, n in rows
        ],
        indent=2,
    )


@mcp.tool()
def query_auth_events(host: str) -> str:
    """Return recent authentication events for a host (who is logged on to it)."""
    rows = [r for r in AUTH_EVENTS if r[1] == host]
    return json.dumps(
        [
            {"at": t, "host": h, "user": u, "event": e, "result": res}
            for t, h, u, e, res in rows
        ],
        indent=2,
    )


if __name__ == "__main__":
    mcp.run()
