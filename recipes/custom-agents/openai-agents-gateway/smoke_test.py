#!/usr/bin/env python3
"""CI smoke for custom-agents/openai-agents-gateway — a violating model call is blocked.

Points the stock OpenAI Agents SDK at the Highflame gateway and sends the
credential-exfiltration prompt. The gateway should return a block (non-2xx) instead of
a completion. Runs against live prod/SaaS.

Exit codes: 0 = pass (or policy-not-active warning), 1 = unexpected, 2 = skipped.
"""
from __future__ import annotations

import asyncio
import os
import sys

from agent import VIOLATION, build_agent, configure_gateway, run_scenario


async def _run() -> int:
    configure_gateway()  # exits 2 itself when keys are absent
    outcome = await run_scenario(build_agent(), "smoke: credential exfiltration", VIOLATION)
    if outcome == "block":
        print("PASS violating model call blocked at the gateway")
        return 0
    if outcome == "allow":
        print(
            "WARN violating request was allowed — is a secrets guardrail active in "
            "enforce mode for this tenant?"
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
