"""Smoke test for the Cost Controls LiteLLM notebook. It reads the budget and reports a $0 call,
as the guardrail does with `report_usage: true`.

It never spends anything and never uses up a budget: the scheduled CI run shares a tenant with
every other recipe, and a used-up budget would block their prompts for the rest of the day.

Exit 0 on success, 1 on failure, 2 when credentials are absent (skip).
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

if not os.environ.get("HIGHFLAME_API_KEY"):
    print("SKIP: not set: HIGHFLAME_API_KEY")
    sys.exit(2)

from highflame import Highflame

API_URL = os.environ.get("HIGHFLAME_API_URL", "https://api.highflame.ai").rstrip("/")
AUTH_URL = os.environ.get("HIGHFLAME_AUTH_URL", "https://auth.highflame.ai").rstrip("/")

try:
    client = Highflame(
        api_key=os.environ["HIGHFLAME_API_KEY"],
        base_url=API_URL,
        identity_base_url=AUTH_URL,
        token_url=f"{AUTH_URL}/oauth2/token",
    )

    # One input token of gpt-4o-mini prices below one micro-dollar, so this records a $0 call.
    report = client.usage.report(model="gpt-4o-mini", provider="openai", input_tokens=1)
    if not report.priced:
        print("FAIL: Highflame did not find gpt-4o-mini in its price table")
        sys.exit(1)
    print(f"OK: usage report accepted, recorded={report.recorded}, cost=${report.cost_micros / 1e6:.6f}")

    # A read, never a block: monitor mode, and no tokens.
    decision = client.guard.evaluate_prompt("budget check", mode="monitor", debug=True)
    seen = {**(decision.context or {}), **(decision.projected_context or {})}
    if "budget_cost_pct_daily" in seen:
        print(
            f"OK: daily budget {seen['budget_cost_pct_daily']}% used,"
            f" used up={seen.get('budget_exceeded_daily', False)}"
        )
    else:
        print("OK: this project has no daily budget, so there is nothing to read")
except Exception as exc:  # noqa: BLE001
    # Type and status only, so no key material reaches the CI log.
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    print(f"FAIL: {type(exc).__name__}" + (f" (HTTP {status})" if status else ""))
    sys.exit(1)
