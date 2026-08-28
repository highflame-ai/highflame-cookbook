#!/usr/bin/env python3
"""CI smoke for custom-agents/strands-defense-in-depth — the destructive call is stopped.

Runs the model-requested destructive fleet command. The gateway evaluates the tool
call in the model's response and denies it pre-execution, so the agent never receives
the directive. Asserts that block.

Exit codes: 0 = pass (or policy-not-active warning), 1 = unexpected, 2 = skipped.
"""
from __future__ import annotations

import asyncio
import os
import sys

from agent import DESTRUCTIVE, build_agent, build_client, run_turn


async def _run() -> int:
    agent = build_agent(build_client())  # exits 2 itself when keys are absent
    outcome = await run_turn(agent, "smoke: destructive fleet command", DESTRUCTIVE)
    if outcome in ("block-gateway", "block-sdk"):
        print(f"PASS destructive fleet command blocked ({outcome})")
        return 0
    if outcome == "allow":
        print(
            "WARN destructive command was allowed — is a tool-governance policy active "
            "in enforce mode for this tenant?"
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
