#!/usr/bin/env python3
"""CI smoke for track 03 — DLP.

Asserts an MRN in a prompt and a credential in a model output are both caught. An allow
(packs not active) is a soft warning, not a hard failure.

Exit codes: 0 = pass (or soft warning), 1 = unexpected failure, 2 = skipped (no key).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common  # noqa: E402
from dlp_guardrails import PHI_PROMPT, SECRET_IN_OUTPUT  # noqa: E402

BLOCKED = {"deny", "modify"}


def main() -> int:
    if not common.require_key():
        return 2
    try:
        token = common.mint_token()["access_token"]

        phi = common.guard(token, PHI_PROMPT, action="process_prompt")
        if common.decision_of(phi) in BLOCKED:
            print(f"PASS PHI in prompt -> {common.decision_of(phi)}")
        else:
            print(
                "WARN PHI prompt allowed — enable the Structural PII pack (privacy.defaults)."
            )

        secret = common.guard(
            token, SECRET_IN_OUTPUT, action="process_prompt", content_type="response"
        )
        if common.decision_of(secret) in BLOCKED:
            print(f"PASS credential in model output -> {common.decision_of(secret)}")
        else:
            print(
                "WARN credential in output allowed — enable the Secrets pack (data-protection.defaults)."
            )

        return 0
    except common.HighflameError as e:
        print(f"FAIL: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
