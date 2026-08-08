#!/usr/bin/env python3
"""CI smoke for track 04 — injection & supply chain.

Asserts a direct injection and a poisoned tool description are both caught. An allow (packs
not active) is a soft warning.

Exit codes: 0 = pass (or soft warning), 1 = unexpected failure, 2 = skipped (no key).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common  # noqa: E402
from injection_and_poisoning import DIRECT, POISONED_TOOL  # noqa: E402

BLOCKED = {"deny", "modify"}


def main() -> int:
    if not common.require_key():
        return 2
    try:
        token = common.mint_token()["access_token"]

        direct = common.guard(token, DIRECT, action="process_prompt")
        if common.decision_of(direct) in BLOCKED:
            print(f"PASS direct injection -> {common.decision_of(direct)}")
        else:
            print("WARN direct injection allowed — enable the injection defaults pack.")

        poison = common.guard(
            token,
            "connect the get_weather tool",
            action="connect_server",
            tool=POISONED_TOOL,
        )
        if common.decision_of(poison) in BLOCKED:
            print(f"PASS tool-description poisoning -> {common.decision_of(poison)}")
        else:
            print(
                "WARN poisoned tool description allowed — enable the tool-safety pack."
            )

        return 0
    except common.HighflameError as e:
        print(f"FAIL: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
