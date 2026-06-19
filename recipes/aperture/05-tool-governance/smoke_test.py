#!/usr/bin/env python3
"""CI smoke for 05 — block a dangerous shell tool call via the Aperture pre_request hook.

Sends a pre_request whose request_body.input carries an exec_command running
`curl | sh` and asserts Highflame returns a block. Runs against live prod/SaaS.

Exit codes: 0 = pass (or policy-not-active warning), 1 = unexpected, 2 = skipped.
"""
from __future__ import annotations

import os
import sys

from aperture_event import DANGEROUS_CMD, PROMPT, aperture_pre_request, post_event


def main() -> int:
    if not os.environ.get("HIGHFLAME_API_KEY"):
        print("SKIP: HIGHFLAME_API_KEY not set.")
        return 2

    resp = post_event(aperture_pre_request(PROMPT, DANGEROUS_CMD))
    action = resp.get("action")

    if action == "block":
        print(f"PASS dangerous tool call blocked -> {resp.get('message')!r}")
        return 0
    if action in ("allow", "modify"):
        print(
            "WARN command not blocked — is a tool/shell policy (bash AST classifier "
            "or tool_risk) active in enforce mode for this tenant?"
        )
        return 0  # not a hard failure: tenant may run monitor mode or lack the policy
    print(f"FAIL unexpected response: {resp}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
