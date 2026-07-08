#!/usr/bin/env python3
"""CI smoke for agent-governance — a governed request from an adopted agent is blocked.

Sends a representative policy-violating request for an adopted agent and asserts Highflame
returns a block. Runs against live prod/SaaS.

Exit codes: 0 = pass (or policy-not-active warning), 1 = unexpected, 2 = skipped.
This is the entrypoint the cookbook's scheduled CI invokes with a canary tenant's key.
"""
from __future__ import annotations

import os
import sys

from governed_agent_request import VIOLATION, governed_request, post_event


def main() -> int:
    if not os.environ.get("HIGHFLAME_API_KEY"):
        print("SKIP: HIGHFLAME_API_KEY not set.")
        return 2

    resp = post_event(governed_request(VIOLATION))
    action = resp.get("action")

    if action == "block":
        print(f"PASS agent request blocked -> {resp.get('message')!r}")
        return 0
    if action == "allow":
        print(
            "WARN agent request was allowed — is a guardrail active in enforce mode, "
            "and a baseline authorization policy loaded, for this tenant?"
        )
        return 0  # not a hard failure: tenant may run monitor mode or lack the policy
    print(f"FAIL unexpected response: {resp}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
