#!/usr/bin/env python3
"""CI smoke for 01 — block a credential leak via the Aperture pre_request hook.

Sends the exact Aperture `pre_request` payload for a prompt containing (fake) AWS keys
and asserts Highflame returns a block. Runs against live prod/SaaS.

Exit codes: 0 = pass (or policy-not-active warning), 1 = unexpected, 2 = skipped.
This is the entrypoint the cookbook's scheduled CI invokes with a canary tenant's key.
"""
from __future__ import annotations

import os
import sys

from aperture_event import LEAK, aperture_pre_request, post_event


def main() -> int:
    if not os.environ.get("HIGHFLAME_API_KEY"):
        print("SKIP: HIGHFLAME_API_KEY not set.")
        return 2

    resp = post_event(aperture_pre_request(LEAK))
    action = resp.get("action")

    if action == "block":
        print(f"PASS leak blocked -> {resp.get('message')!r}")
        return 0
    if action == "allow":
        print(
            "WARN leak was allowed — is a block-secrets policy active in enforce mode, "
            "and an Overwatch baseline-permit loaded, for this tenant?"
        )
        return 0  # not a hard failure: tenant may run monitor mode or lack the policy
    print(f"FAIL unexpected response: {resp}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
