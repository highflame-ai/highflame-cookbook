#!/usr/bin/env python3
"""Pull Highflame Observatory cost and productivity metrics over the HTTP API.

Companion to export_events.py, which exports raw event rows. This script
pulls the aggregate reports instead — the same numbers the Studio dashboards
render, in a shape you can feed to a spreadsheet or an LLM.

It reuses the auth path from export_events.py: a zid_sk_* key is exchanged
for a JWT at AuthN, and the JWT goes to Observatory as a bearer token.

Reports
-------
  cost          Spend by product and by model, plus per-model rollups.
  usage         Per-developer activity: events, tokens, threats, blocks.
  productivity  Commits, PRs, issues closed, lines changed, active developers.

Examples
--------
  export HIGHFLAME_API_KEY=zid_sk_...

  # Everything for the last 30 days, human-readable.
  ./usage_report.py --since 30d

  # One JSON document for an LLM to analyse.
  ./usage_report.py --since 30d --format json -o report.json

  # Just the per-developer breakdown.
  ./usage_report.py --report usage --since 7d
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# Reuse the client pieces rather than duplicating them. export_events.py
# guards its CLI behind __main__, so importing it runs no side effects.
from export_events import (  # noqa: E402
    DEFAULT_API_URL,
    DEFAULT_AUTH_URL,
    ObservatoryError,
    decode_jwt_claims,
    mint_token,
    parse_since,
    read_tenant,
    request_json,
    rfc3339,
)

QUERY_PATH = "/v1/obs/query"
COSTS_PATH = "/v1/obs/costs/intelligence"

# ViewQL result rows come back columnar. Every helper below re-shapes them
# into dicts so the output is self-describing.


class Client:
    """Thin Observatory client bound to one tenant-scoped token."""

    def __init__(self, api_url: str, token: str, verbose: bool = False):
        self.api_url = api_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.verbose = verbose

    def costs(self, start: str, end: str) -> dict:
        import urllib.parse
        query = urllib.parse.urlencode({"start": start, "end": end})
        return request_json(f"{self.api_url}{COSTS_PATH}?{query}",
                            headers=self.headers)

    def query(self, body: dict) -> list[dict]:
        """Run one ViewQL query and return its rows as dicts."""
        if self.verbose:
            print(f"viewql: {body['view']} {body.get('measures')}",
                  file=sys.stderr)
        result = request_json(
            f"{self.api_url}{QUERY_PATH}",
            data=json.dumps(body).encode("utf-8"),
            headers=self.headers,
            method="POST",
        )
        names = [column["name"] for column in (result.get("columns") or [])]
        return [dict(zip(names, row)) for row in (result.get("rows") or [])]

    def scalar(self, view: str, measures: list[str], time_range: dict) -> dict:
        """Run a chart_type=number query and return the single result row."""
        rows = self.query({
            "view": view,
            "chart_type": "number",
            "measures": measures,
            "time_range": time_range,
        })
        return rows[0] if rows else {measure: 0 for measure in measures}

    def table(self, view: str, dimensions: list[str], measures: list[str],
              time_range: dict, *, order_by: str | None = None,
              limit: int | None = None) -> list[dict]:
        body = {
            "view": view,
            "chart_type": "table",
            "dimensions": dimensions,
            "measures": measures,
            "time_range": time_range,
        }
        if order_by:
            body["order_by"] = [{"name": order_by, "desc": True}]
        if limit:
            body["limit"] = limit
        return self.query(body)


def report_cost(client: Client, start: str, end: str,
                time_range: dict) -> dict:
    """Spend, from the dedicated endpoint plus the hourly rollup view."""
    intelligence = client.costs(start, end)
    return {
        "total_cost_usd": intelligence.get("total_cost_usd", 0),
        "total_detections": intelligence.get("total_detections", 0),
        "by_product": intelligence.get("by_product") or [],
        "by_model": intelligence.get("by_model") or [],
        # cost_hourly carries request counts and latency the endpoint omits.
        "by_model_detail": client.table(
            "cost_hourly",
            ["model_provider", "model_name", "product"],
            ["request_count", "tokens_in", "tokens_out", "total_cost",
             "avg_latency"],
            time_range,
            order_by="total_cost",
        ),
    }


def report_usage(client: Client, time_range: dict) -> dict:
    """Per-developer activity — the abuse and waste question LMI asked about."""
    per_user = client.table(
        "user_daily",
        ["user_id", "source_ide", "product"],
        ["event_count", "threat_events", "blocked_events", "total_tokens",
         "total_duration"],
        time_range,
        order_by="total_tokens",
    )
    totals = client.scalar(
        "user_daily",
        ["event_count", "threat_events", "blocked_events", "total_tokens"],
        time_range,
    )
    return {
        "totals": totals,
        "active_developers": len({row.get("user_id") for row in per_user
                                  if row.get("user_id")}),
        "per_user": per_user,
    }


def report_productivity(client: Client, time_range: dict) -> dict:
    """Git outcomes attributed to AI sessions, matching Studio's panel."""
    kpis = client.scalar(
        "git_events",
        ["commits", "prs_created", "prs_merged", "prs_closed",
         "issues_closed", "shipping_sessions", "active_developers",
         "total_lines_added", "total_lines_removed"],
        time_range,
    )
    sessions = client.scalar("events", ["unique_sessions"], time_range)
    kpis["total_sessions"] = sessions.get("unique_sessions", 0)

    total = kpis.get("total_sessions") or 0
    shipping = kpis.get("shipping_sessions") or 0
    kpis["shipping_session_ratio"] = round(shipping / total, 4) if total else 0

    return {
        "kpis": kpis,
        "by_repo": client.table(
            "git_events", ["repo"],
            ["count", "commits", "prs_merged", "total_lines_added",
             "total_lines_removed"],
            time_range, order_by="count", limit=25),
        "by_developer": client.table(
            "git_events", ["user_id", "user_name"],
            ["commits", "prs_created", "prs_merged", "issues_closed",
             "total_lines_added", "total_lines_removed"],
            time_range, order_by="commits", limit=200),
    }


def render_rows(rows: list[dict], stream, indent: str = "  ") -> None:
    """Print a list of dicts as an aligned text table."""
    if not rows:
        print(f"{indent}(no rows)", file=stream)
        return
    columns = list(rows[0])
    widths = {c: max(len(c), *(len(format_cell(r.get(c))) for r in rows))
              for c in columns}
    print(indent + "  ".join(c.ljust(widths[c]) for c in columns), file=stream)
    print(indent + "  ".join("-" * widths[c] for c in columns), file=stream)
    for row in rows:
        print(indent + "  ".join(
            format_cell(row.get(c)).ljust(widths[c]) for c in columns),
            file=stream)


def format_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:,.4f}" if abs(value) < 1 else f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def render_text(report: dict, stream) -> None:
    meta = report["meta"]
    print(f"Highflame Observatory report", file=stream)
    print(f"  account_id  {meta['account_id']}", file=stream)
    print(f"  project_id  {meta['project_id'] or '(empty)'}", file=stream)
    print(f"  window      {meta['start']} to {meta['end']}", file=stream)

    if "cost" in report:
        cost = report["cost"]
        print(f"\n== Cost ==", file=stream)
        print(f"  total spend      ${cost['total_cost_usd']:,.2f}", file=stream)
        print(f"  total detections {cost['total_detections']:,}", file=stream)
        print(f"\n  By product:", file=stream)
        render_rows(cost["by_product"], stream, indent="    ")
        print(f"\n  By model:", file=stream)
        render_rows(cost["by_model_detail"], stream, indent="    ")

    if "usage" in report:
        usage = report["usage"]
        print(f"\n== Developer usage ==", file=stream)
        print(f"  active developers {usage['active_developers']:,}",
              file=stream)
        for name, value in usage["totals"].items():
            print(f"  {name:<18}{format_cell(value)}", file=stream)
        print(f"\n  Per developer:", file=stream)
        render_rows(usage["per_user"], stream, indent="    ")

    if "productivity" in report:
        prod = report["productivity"]
        print(f"\n== Productivity ==", file=stream)
        for name, value in prod["kpis"].items():
            print(f"  {name:<24}{format_cell(value)}", file=stream)
        print(f"\n  By repo:", file=stream)
        render_rows(prod["by_repo"], stream, indent="    ")
        print(f"\n  By developer:", file=stream)
        render_rows(prod["by_developer"], stream, indent="    ")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pull Observatory cost and productivity metrics.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Examples")[-1],
    )
    parser.add_argument("--api-key", default=os.environ.get("HIGHFLAME_API_KEY"),
                        help="zid_sk_* key (default: $HIGHFLAME_API_KEY)")
    parser.add_argument("--auth-url", default=os.environ.get(
        "HIGHFLAME_AUTH_URL", DEFAULT_AUTH_URL))
    parser.add_argument("--api-url", default=os.environ.get(
        "HIGHFLAME_API_URL", DEFAULT_API_URL))

    parser.add_argument("--report", choices=("cost", "usage", "productivity",
                                             "all"), default="all")
    parser.add_argument("--since", type=parse_since, default=parse_since("30d"),
                        help="relative window ending now, e.g. 24h, 30d "
                             "(default: 30d)")
    parser.add_argument("--start", help="RFC3339 start; overrides --since")
    parser.add_argument("--end", help="RFC3339 end (default: now)")

    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("-o", "--out", help="output file (default: stdout)")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()
    if not args.api_key:
        parser.error("no API key; pass --api-key or set HIGHFLAME_API_KEY")

    now = datetime.now(timezone.utc)
    end = args.end or rfc3339(now)
    start = args.start or rfc3339(now - args.since)
    time_range = {"start": start, "end": end}

    try:
        token = mint_token(args.auth_url, args.api_key)
        claims = decode_jwt_claims(token)
        account_id, project_id = read_tenant(claims)
        if not account_id:
            raise ObservatoryError(
                "the minted token carries no account_id claim. Claims "
                "present: " + ", ".join(sorted(claims)))
        if args.verbose:
            print(f"scope: account_id={account_id} "
                  f"project_id={project_id or '(empty)'}", file=sys.stderr)

        client = Client(args.api_url, token, verbose=args.verbose)
        report: dict = {"meta": {
            "account_id": account_id,
            "project_id": project_id,
            "start": start,
            "end": end,
            "generated_at": rfc3339(now),
        }}
        if args.report in ("cost", "all"):
            report["cost"] = report_cost(client, start, end, time_range)
        if args.report in ("usage", "all"):
            report["usage"] = report_usage(client, time_range)
        if args.report in ("productivity", "all"):
            report["productivity"] = report_productivity(client, time_range)

        stream = open(args.out, "w") if args.out else sys.stdout
        try:
            if args.format == "json":
                json.dump(report, stream, indent=2)
                stream.write("\n")
            else:
                render_text(report, stream)
        finally:
            if args.out:
                stream.close()
    except ObservatoryError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130

    if args.out:
        print(f"wrote {args.report} report ({start} to {end}) to {args.out}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
