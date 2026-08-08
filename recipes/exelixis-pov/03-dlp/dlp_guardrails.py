#!/usr/bin/env python3
"""Track 03 — DLP (use cases 10, 11).

  UC10  Regulated data and credentials are caught on EVERY surface — the prompt, the model's
        output, and a tool's output — by the same policy.
  UC11  Custom formats (an internal case id, a brand-restricted term) are configurable.

All data here is FICTIONAL: an invented MRN, AWS's documented example key, an invented
`EXL-####` study id. Never put real PHI or credentials in a prompt.

Runs against Highflame SaaS by default. Needs HIGHFLAME_API_KEY (a zid_sk_ service key) and
an active PII/Secrets guardrail pack. UC11's custom regex must be provisioned first (see
README); until then the script reports the EXL-#### id as "not yet configured" rather than
failing.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common  # noqa: E402

# Fictional pharma chart note — trips medical_record (MRN), plus clinical context.
PHI_PROMPT = (
    "Summarise this chart note for the trial coordinator: patient chart 4827193, "
    "MRN 4827193, blood type O+, primary diagnosis carcinoma, on chemotherapy since 2025-11-02."
)
# AWS's own documented example values — trip the secret detector without being real.
SECRET_IN_OUTPUT = (
    "Here is the config you asked me to echo: "
    "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE "
    "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
)
# A tool result (e.g. a CRM row) that carries an MRN back toward the model.
PHI_IN_TOOL_OUTPUT = (
    '{"row": {"name": "J. Marlow", "mrn": "MRN 4827193", "dx": "carcinoma"}}'
)
# The internal identifier UC11 is about.
CASE_ID_TEXT = "Pull the safety narrative for case EXL-4471 before the review."
CASE_ID_REGEX = os.environ.get("EXELIXIS_CASE_ID_REGEX", r"\bEXL-\d{4}\b")


def uc10_prompt(token: str) -> None:
    common.banner("UC10 · PHI in a prompt")
    resp = common.guard(token, PHI_PROMPT, action="process_prompt")
    common.show(resp)
    print(
        "  Flip the medical-identifier rule's effect to `mask` in Studio and this returns\n"
        "  decision=modify with the MRN masked — the model still answers, PHI never leaves."
    )


def uc10_model_output(token: str) -> None:
    common.banner("UC10 · credential in a MODEL OUTPUT")
    # content_type="response" evaluates text on the way BACK from the model.
    resp = common.guard(
        token, SECRET_IN_OUTPUT, action="process_prompt", content_type="response"
    )
    common.show(resp)
    print(
        "  Caught on the egress path — the credential is stopped on the way out.\n"
        "  Caveat to state: secrets are BLOCK-ONLY (never masked-and-forwarded); PII/PHI is\n"
        "  fully redactable. See GAP-ANALYSIS (G-UC10)."
    )


def uc10_tool_output(token: str) -> None:
    common.banner("UC10 · PHI in a TOOL OUTPUT")
    resp = common.guard(
        token, PHI_IN_TOOL_OUTPUT, action="call_tool", content_type="response"
    )
    common.show(resp)
    print(
        "  The SAME medical-identifier policy covers this surface — its action list already\n"
        "  includes call_tool, so no new rule is needed for tool results. That one policy\n"
        "  covering prompt + model-output + tool-output is the strongest point of UC10."
    )


def uc11_custom_id(token: str) -> None:
    common.banner("UC11 · custom identifier (EXL-####)")
    print(
        f"  local pattern check: EXL id present = {bool(re.search(CASE_ID_REGEX, CASE_ID_TEXT))}"
    )
    resp = common.guard(token, CASE_ID_TEXT, action="process_prompt")
    verdict = common.decision_of(resp)
    common.show(resp)
    if verdict in ("deny", "modify"):
        print("  Custom EXL-#### detection is provisioned and firing.")
    else:
        print(
            "  Not yet caught — the custom pattern is not provisioned for this tenant.\n"
            "  UC11's engine is fully supported (per-tenant, hot-reloaded custom regex +\n"
            "  keyword libraries), but there is no Studio UI for custom REGEX yet, so you add\n"
            "  it via the Admin policy API. IMPORTANT: the custom-pattern write REPLACES the\n"
            "  built-in set, so read-modify-write (append your pattern to the existing ones).\n"
            "  Full steps + the read-modify-write recipe in README (UC11) and GAP-ANALYSIS (G-UC11)."
        )


def main() -> int:
    if not common.require_key():
        return 2
    try:
        token = common.mint_token()["access_token"]
        uc10_prompt(token)
        uc10_model_output(token)
        uc10_tool_output(token)
        uc11_custom_id(token)
    except common.HighflameError as e:
        print(f"\nFAIL: {e}")
        return 1
    print("\nDone. Verify redactions/blocks in Studio -> Observatory.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
