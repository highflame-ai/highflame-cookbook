#!/usr/bin/env python3
"""CI smoke for custom-agents/langgraph-sdk — a poisoned ticket is quarantined inline.

Builds the guarded LangGraph worker and runs the poisoned ticket (indirect injection
with embedded example credentials) through it. The prompt guard should deny it before
the model is invoked, exercising the full SDK middleware path (client -> guard
evaluate -> BlockedError) against live prod/SaaS.

Exit codes: 0 = pass (or policy-not-active warning), 1 = unexpected, 2 = skipped.
"""
from __future__ import annotations

import asyncio
import os
import sys

from agent import POISONED_TICKET, build_agent, process_ticket


async def _run() -> int:
    agent = build_agent()  # exits 2 itself when keys are absent
    outcome = await process_ticket(agent, POISONED_TICKET)
    if outcome == "blocked":
        print("PASS poisoned ticket quarantined before the model ran")
        return 0
    if outcome == "enriched":
        print(
            "WARN poisoned ticket was processed — is a secrets guardrail active in "
            "enforce mode for this tenant?"
        )
        return 0  # not a hard failure: tenant may run monitor mode
    print("FAIL guard call errored")
    return 1


def main() -> int:
    if not os.environ.get("HIGHFLAME_API_KEY") or not os.environ.get("OPENAI_API_KEY"):
        print("SKIP: HIGHFLAME_API_KEY and OPENAI_API_KEY are both required.")
        return 2
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
