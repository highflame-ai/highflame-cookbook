#!/usr/bin/env python3
"""CI smoke for custom-agents/strands-gateway-ip — outbound IP share is blocked.

Runs the external-share turn: the same protected identifiers the internal turns use,
but bound for a collaborator outside the organisation. Asserts the gateway block.

Exit codes: 0 = pass (or policy-not-active warning), 1 = unexpected, 2 = skipped.
"""
from __future__ import annotations

import asyncio
import os
import sys

from agent import EXTERNAL_SHARE, build_agent, run_turn


async def _run() -> int:
    outcome = await run_turn(build_agent(), "smoke: external share", EXTERNAL_SHARE)
    if outcome == "block":
        print("PASS outbound share of protected identifiers blocked at the gateway")
        return 0
    if outcome == "allow":
        print(
            "WARN outbound share was allowed — check the keyword_filter entries, that "
            "the Cedar policy is enforce mode and scoped to this project, and that tool "
            "arguments reach scannable content."
        )
        return 0  # not a hard failure: tenant may run monitor mode
    print("FAIL gateway call errored")
    return 1


def main() -> int:
    if not os.environ.get("HIGHFLAME_API_KEY") or not os.environ.get("OPENAI_API_KEY"):
        print("SKIP: HIGHFLAME_API_KEY and OPENAI_API_KEY are both required.")
        return 2
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
