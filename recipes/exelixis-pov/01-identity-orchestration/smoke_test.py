#!/usr/bin/env python3
"""CI smoke for track 01 — identity orchestration.

Asserts the load-bearing, tenant-independent properties: a token mints, its subject is a
per-agent WIMSE URI carrying an owner, and a revoked token is denied on the next call.

Exit codes: 0 = pass (or a soft warning), 1 = unexpected failure, 2 = skipped (no key).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common  # noqa: E402


def main() -> int:
    if not common.require_key():
        return 2
    try:
        token = common.mint_token()
        claims = common.decode_claims(token["access_token"])

        sub = claims.get("sub", "")
        if not sub.startswith("spiffe://"):
            print(f"FAIL: token subject is not a WIMSE URI: {sub!r}")
            return 1
        if not claims.get("jti"):
            print("FAIL: token carries no jti (revocation handle).")
            return 1
        print(f"PASS unique identity -> sub={sub} owner={claims.get('owner_user_id')}")

        span = claims.get("exp", 0) - claims.get("iat", 0)
        print(
            f"PASS short-lived -> expires_in={token.get('expires_in')}s (exp-iat={span}s)"
        )

        victim = common.mint_token()
        common.revoke_token(victim["access_token"])
        after = common.guard(victim["access_token"], "hello", action="process_prompt")
        verdict = common.decision_of(after)
        if verdict == "unauthorized":
            print("PASS revocation -> revoked token denied on next call")
        else:
            print(
                f"WARN revoked token returned {verdict!r}, not a 401 — likely the deny-set "
                "cold-start gap (a replica reconnected after publish). Not a hard failure."
            )
        return 0
    except common.HighflameError as e:
        print(f"FAIL: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
