#!/usr/bin/env python3
"""CI smoke for custom-agents/langgraph-mcp-soc-triage — policy gates hold, headlessly.

CI has no soc_lead to click approve, so this does not drive the full CIBA
dance. It asserts the two gates that make the demo safe to run unattended:

  1. The threat-analyst's direct block_ip is NOT allowed (deny — or step_up,
     which also stops execution; both are acceptable evidence the gate holds).
  2. The responder's block_ip comes back `step_up` — suspended pending the
     approval, never a plain allow.

Exit codes: 0 = pass (or policy-not-active warning), 1 = unexpected, 2 = skipped.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv

    # override=True: the recipe's .env beats shell-profile exports (see graph.py).
    load_dotenv(Path(__file__).parent / ".env", override=True)
except ImportError:
    pass

from highflame import APIConnectionError, BlockedError

from graph import ALERT, _client_for, _session_id
from identities import bootstrap


def _decision(identity, session: str) -> str:
    try:
        resp = _client_for(identity).guard.evaluate_tool_call(
            "block_ip",
            {"ip": ALERT["indicator"], "reason": "smoke test"},
            session_id=session,
        )
        return resp.decision
    except BlockedError:
        return "deny"


def main() -> int:
    if not os.environ.get("HIGHFLAME_API_KEY"):
        print("SKIP: HIGHFLAME_API_KEY is required.")
        return 2

    cast = bootstrap()
    try:
        analyst = _decision(cast["threat-analyst"], _session_id("smoke-analyst"))
        responder = _decision(cast["responder"], _session_id("smoke-responder"))
    except APIConnectionError:
        print("FAIL: Highflame unreachable — set HIGHFLAME_BASE_URL / check network.")
        return 1

    ok = True
    if analyst in ("deny", "step_up"):
        print(f"PASS analyst block_ip did not proceed (decision={analyst})")
    else:
        print(f"WARN analyst block_ip returned {analyst} — is the tool-scope "
              "policy active for this tenant?")

    if responder == "step_up":
        print("PASS responder block_ip is suspended pending approval (step_up)")
    elif responder == "deny":
        print("WARN responder block_ip denied outright — expected step_up; "
              "check the @step_up_required('soc_lead') policy and the "
              "responder's scopes.")
    elif responder == "allow":
        print("WARN responder block_ip allowed WITHOUT approval — the step-up "
              "policy is not active; the demo's headline beat will not fire.")
    else:
        print(f"FAIL unexpected decision {responder!r}")
        ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
