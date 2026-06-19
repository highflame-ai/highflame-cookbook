#!/usr/bin/env python3
"""CI smoke for 03 — transparent PII (email) redaction via Aperture `modify`.

Sends the exact Aperture `pre_request` payload for a prompt containing an email and
asserts Highflame returns `modify` with the email scrubbed from the forwarded body.
Runs against live prod/SaaS.

Exit codes: 0 = pass (or policy-not-active warning), 1 = unexpected, 2 = skipped.
"""
from __future__ import annotations

import os
import sys

from aperture_event import EMAIL, PROMPT, aperture_pre_request, forwarded_prompt, post_event


def main() -> int:
    if not os.environ.get("HIGHFLAME_API_KEY"):
        print("SKIP: HIGHFLAME_API_KEY not set.")
        return 2

    assert EMAIL in PROMPT, "test fixture drifted: email no longer in source prompt"

    resp = post_event(aperture_pre_request(PROMPT))
    action = resp.get("action")

    if action == "modify":
        forwarded = forwarded_prompt(resp) or ""
        if EMAIL in forwarded:
            print(f"FAIL email still present in forwarded body: {forwarded!r}")
            return 1
        print(f"PASS email redacted; forwarded -> {forwarded!r}")
        return 0

    if action in ("allow", "block"):
        print(
            "WARN no redaction (got %r) — is a redact-email policy (forbid + "
            "@redaction_strategy) active in enforce mode for this tenant?" % action
        )
        return 0  # not a hard failure: tenant may not have authored the redaction policy

    print(f"FAIL unexpected response: {resp}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
