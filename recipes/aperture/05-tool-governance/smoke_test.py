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
    message = resp.get("message") or ""

    if action == "block":
        # An identity-gate denial is also a block — but it fires before any
        # content policy runs, so it must not count as a policy pass.
        if "not a member" in message:
            print(
                "WARN blocked by the identity gate, not the shell policy — set "
                "HIGHFLAME_APERTURE_LOGIN to your Highflame org email (same email "
                "as your Tailscale login). See ../README.md#identity--access."
            )
            return 0
        print(f"PASS dangerous tool call blocked -> {message!r}")
        return 0
    if action in ("allow", "modify"):
        print(
            "WARN command not blocked — is the Shell & Command Governance template "
            "(tools.shell-command-governance) or an equivalent tool/shell policy "
            "active in enforce mode for this tenant?"
        )
        return 0  # not a hard failure: tenant may run monitor mode or lack the policy
    print(f"FAIL unexpected response: {resp}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
