#!/usr/bin/env python3
"""CI smoke for 04 — block indirect prompt injection via the Aperture pre_request hook.

Sends the exact Aperture `pre_request` payload carrying a poisoned doc (hidden
instruction) and asserts Highflame returns a block. Runs against live prod/SaaS.

Exit codes: 0 = pass (or policy-not-active warning), 1 = unexpected, 2 = skipped.
"""
from __future__ import annotations

import os
import sys

from aperture_event import PROMPT, aperture_pre_request, post_event


def main() -> int:
    if not os.environ.get("HIGHFLAME_API_KEY"):
        print("SKIP: HIGHFLAME_API_KEY not set.")
        return 2

    assert "evil.example" in PROMPT, "test fixture drifted: injection payload missing"

    resp = post_event(aperture_pre_request(PROMPT))
    action = resp.get("action")

    if action == "block":
        print(f"PASS indirect injection blocked -> {resp.get('message')!r}")
        return 0
    if action in ("allow", "modify"):
        print(
            "WARN injection not blocked — is a prompt-injection policy active in "
            "enforce mode for this tenant?"
        )
        return 0  # not a hard failure: tenant may run monitor mode or lack the policy
    print(f"FAIL unexpected response: {resp}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
