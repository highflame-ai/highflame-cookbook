#!/usr/bin/env python3
"""CI smoke test for the Enterprise-Managed Authorization recipe — runs against live SaaS.

Confirms your Highflame MCP endpoint advertises Enterprise-Managed Authorization, so an
EMA-capable client will discover it and take the IdP (Okta Cross-App Access) path:
  * its protected-resource metadata (RFC 9728) names an authorization server, and
  * it advertises the `enterprise-managed-authorization` MCP extension.

Exit codes: 0 = pass, 1 = assertion failed, 2 = missing config (skipped, not failed).
Stdlib only — no third-party dependencies.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

EMA_EXTENSION = "io.modelcontextprotocol/enterprise-managed-authorization"
WELL_KNOWN = "/.well-known/oauth-protected-resource"


def main() -> int:
    base = os.environ.get("HIGHFLAME_MCP_RESOURCE_URL", "").rstrip("/")
    if not base:
        print("SKIP: HIGHFLAME_MCP_RESOURCE_URL not set.")
        return 2

    url = base + WELL_KNOWN
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310 — fixed https base
            meta = json.load(resp)
    except (urllib.error.URLError, ValueError) as exc:
        print(f"FAIL could not fetch protected-resource metadata at {url}: {exc}")
        return 1

    auth_servers = meta.get("authorization_servers") or []
    extensions = meta.get("extensions") or {}

    ok = True
    if auth_servers:
        print(f"PASS authorization server advertised: {auth_servers[0]}")
    else:
        print("FAIL no authorization_servers in protected-resource metadata")
        ok = False

    if EMA_EXTENSION in extensions:
        print(f"PASS Enterprise-Managed Authorization advertised ({EMA_EXTENSION})")
    else:
        print(
            "FAIL Enterprise-Managed Authorization extension not advertised — "
            "EMA may not be enabled on this tenant yet (preview)."
        )
        ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
