#!/usr/bin/env python3
"""Track 01 — Identity Orchestration (use cases 2, 4, 5; pointers for 1, 3, 6).

Proves, against a live tenant, the identity properties a service key can prove on its own:

  UC2  This agent has a UNIQUE identity — the token's `sub` is its own WIMSE URI, owned by
       a named human, not a shared account.
  UC4  The credential is SHORT-LIVED — a one-hour token, and requesting a narrow scope
       yields a read-only credential that Shield refuses to let write.
  UC5  The credential is REVOCABLE ahead of expiry — revoke it, and the very next call 401s.

Use cases 1 (discovery), 3 (sub-agent attenuation), and 6 (delegation chain) need two
registered identities with enrolled keys, so they are driven from Studio; this script prints
exactly where. See README.md.

Runs against Highflame SaaS by default. Needs HIGHFLAME_API_KEY (a zid_sk_ service key).
"""

from __future__ import annotations

import os
import sys

# Make `common.py` (one directory up) importable regardless of the working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common  # noqa: E402


def uc2_unique_identity(token: dict) -> dict:
    """UC2 — the token's claims ARE the unique-identity proof."""
    common.banner("UC2 · unique per-agent identity")
    claims = common.decode_claims(token["access_token"])
    print(f"  sub (WIMSE URI): {claims.get('sub')}")
    print(f"  external_id:     {claims.get('external_id')}")
    print(
        f"  identity_type:   {claims.get('identity_type')}  sub_type: {claims.get('sub_type')}"
    )
    print(
        f"  owner_user_id:   {claims.get('owner_user_id')}   <- the accountable human"
    )
    print(
        f"  jti:             {claims.get('jti')}   <- the per-credential revocation handle"
    )
    print(
        "\n  The subject is THIS identity's WIMSE URI. Uniqueness is a database constraint\n"
        "  (UNIQUE account_id, project_id, external_id) — registering the same external_id\n"
        "  twice returns 409. It is enforced, not a convention. See README (UC2)."
    )
    return claims


def uc4_short_lived(token: dict) -> None:
    """UC4a — the token is short-lived (default 1 hour), clamped by identity/key expiry."""
    common.banner("UC4 · short-lived credential")
    claims = common.decode_claims(token["access_token"])
    ttl = token.get("expires_in")
    span = (claims.get("exp", 0) - claims.get("iat", 0)) or ttl
    print(f"  expires_in: {ttl}s   (exp - iat = {span}s)")
    print(
        f"  scopes on the full token: {claims.get('scopes') or claims.get('scope') or '[]'}"
    )
    print(
        "\n  Default TTL is 3600s and is clamped DOWN by the identity's and the key's own\n"
        "  expiry — a 20-minute key can never mint a 1-hour token."
    )


def uc4_task_scoped() -> None:
    """UC4b — a read-only credential is refused a write-class action, before any model runs."""
    common.banner("UC4 · task-scoped: a read-only token cannot call a tool")
    read_only = common.mint_token(scope="mcp:read")
    claims = common.decode_claims(read_only["access_token"])
    scopes = claims.get("scopes") or claims.get("scope") or []
    print(f"  minted a token requesting scope=mcp:read -> got scopes: {scopes}")

    if not scopes:
        print(
            "  WARN: the minted token carries no scopes claim, so Shield applies no scope\n"
            "  ceiling (empty scopes = unrestricted, by design). To demo this cleanly, attach\n"
            "  a credential policy with allowed_scopes to the identity. Skipping the assertion."
        )
        return

    tok = read_only["access_token"]
    allow = common.guard(tok, "Summarise the latest run.", action="process_prompt")
    print("  read action (process_prompt, needs mcp:read):")
    common.show(allow)
    deny = common.guard(
        tok, '{"cmd": "rm -rf /data"}', action="call_tool", content_type="tool_call"
    )
    print("  write action (call_tool, needs mcp:execute):")
    common.show(deny)
    if common.decision_of(deny) == "deny":
        print(
            "\n  The write was denied on the SCOPE CEILING — before detectors, before Cedar,\n"
            "  with a signed receipt. Honest note: this is coarse OAuth-scope scoping\n"
            "  (read vs execute), not per-task authorization. True per-task grants (RFC 9396\n"
            "  RAR — 'may call transfer_funds for $500') exist only behind a human CIBA\n"
            "  approval today, not on the machine token endpoint. See GAP-ANALYSIS (G-UC4)."
        )


def uc5_revocation(token: dict) -> None:
    """UC5 — revoke a token; the next call is denied ahead of natural expiry."""
    common.banner("UC5 · revocation beats expiry")
    # Mint a throwaway token so we don't revoke the one the other steps use.
    victim = common.mint_token()
    tok = victim["access_token"]
    before = common.guard(tok, "hello", action="process_prompt")
    print("  before revoke:")
    common.show(before)

    status = common.revoke_token(tok)
    print(f"  revoke -> HTTP {status}")

    after = common.guard(tok, "hello", action="process_prompt")
    print("  after revoke (poll ~5s in practice; the deny-set propagates via pub/sub):")
    common.show(after)
    if common.decision_of(after) == "unauthorized":
        print(
            "\n  Denied ahead of the token's natural expiry. For a PARENT identity, revoking it\n"
            "  cascades to every delegated descendant in one atomic statement — the whole tree\n"
            "  dies. That cascade is driven from Studio (needs a delegation tree); see README (UC5)."
        )
    else:
        print(
            "\n  NOTE: the post-revoke call was not yet rejected. Propagation to the enforcement\n"
            "  point is pub/sub (SLO < 5s); a freshly-(re)connected replica can lag until the\n"
            "  token's natural expiry — the documented cold-start gap. Re-run to confirm."
        )


def pointers() -> None:
    common.banner("UC1, UC3, UC6 · driven from Studio (need registered identities)")
    print(
        "  UC1 discovery : Studio -> Registry -> Connectors -> add Entra / Okta / Google.\n"
        "                  Sync, then Registry -> Unmanaged to adopt with an owner.\n"
        "                  Shadow agents seen only in gateway traffic are NOT yet detected\n"
        "                  (ADR 0027, not built) — GAP-ANALYSIS (G-UC1).\n"
        "  UC3 attenuate : Studio -> ZeroID -> Start. Delegate parent -> sub-agent; the scope\n"
        "                  funnel shows attenuation. Request a scope the parent lacks -> 400\n"
        "                  invalid_scope. Enforced server-side at issuance.\n"
        "  UC6 chain     : after a delegated tool call, Studio -> Observatory -> Audit renders\n"
        "                  human -> orchestrator -> sub-agent -> tool call. Note: the gateway\n"
        "                  (MCP) leg drops delegation headers today — GAP-ANALYSIS (G-UC6)."
    )


def main() -> int:
    if not common.require_key():
        return 2
    try:
        token = common.mint_token()
        uc2_unique_identity(token)
        uc4_short_lived(token)
        uc4_task_scoped()
        uc5_revocation(token)
        pointers()
    except common.HighflameError as e:
        print(f"\nFAIL: {e}")
        return 1
    print("\nDone. Verify every step in Studio -> Observatory / Registry.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
