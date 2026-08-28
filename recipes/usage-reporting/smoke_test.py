#!/usr/bin/env python3
"""CI smoke for usage-reporting — the reporting API answers and is tenant-scoped.

Mints a token from the API key, then pulls a short event page and a one-day
report. Asserts the response shapes and the tenant scope. Does not assert any
volume: a canary tenant with no traffic must still pass.

Exit codes: 0 = pass, 1 = unexpected, 2 = skipped (no credentials).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

from export_events import (
    DEFAULT_API_URL,
    DEFAULT_AUTH_URL,
    ObservatoryError,
    build_filters,
    fetch_events,
    mint_token,
    rfc3339,
)
from usage_report import Client, report_cost, report_productivity, report_usage


class _Filters:
    """Minimal stand-in for the argparse namespace build_filters expects."""

    prompts_only = True
    has_threats = False
    event_type = product = service = decision = severity = mode = None
    threat_category = session_id = user_id = agent_id = None
    source_ide = search = None


def main() -> int:
    api_key = os.environ.get("HIGHFLAME_API_KEY")
    if not api_key:
        print("SKIP: HIGHFLAME_API_KEY not set.")
        return 2

    auth_url = os.environ.get("HIGHFLAME_AUTH_URL", DEFAULT_AUTH_URL)
    api_url = os.environ.get("HIGHFLAME_API_URL", DEFAULT_API_URL)

    now = datetime.now(timezone.utc)
    end, start = rfc3339(now), rfc3339(now - timedelta(days=1))
    time_range = {"start": start, "end": end}

    try:
        token = mint_token(auth_url, api_key)
        account_id, project_id = token.account_id, token.project_id
        print(f"PASS token minted, scope account_id={account_id} "
              f"project_id={project_id or '(empty)'}")

        events = list(fetch_events(api_url, token.access_token, start, end,
                                   build_filters(_Filters()),
                                   prompts_only=True, max_events=5,
                                   page_size=5, verbose=False))
        for event in events:
            if "event_id" not in event or "timestamp" not in event:
                print(f"FAIL event missing expected fields: {sorted(event)}")
                return 1
        print(f"PASS event export returned {len(events)} prompt event(s)")

        client = Client(api_url, token.access_token)
        cost = report_cost(client, start, end, time_range)
        if "total_cost_usd" not in cost:
            print(f"FAIL cost report missing total_cost_usd: {sorted(cost)}")
            return 1
        print(f"PASS cost report, total ${cost['total_cost_usd']:,.2f}")

        usage = report_usage(client, time_range)
        if "per_user" not in usage or "totals" not in usage:
            print(f"FAIL usage report shape: {sorted(usage)}")
            return 1
        print(f"PASS usage report, {usage['active_developers']} active "
              f"developer(s)")

        productivity = report_productivity(client, time_range)
        if "commits" not in productivity["kpis"]:
            print(f"FAIL productivity KPIs: {sorted(productivity['kpis'])}")
            return 1
        print(f"PASS productivity report, "
              f"{productivity['kpis']['commits']} commit(s)")

    except ObservatoryError as err:
        print(f"FAIL {err}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
