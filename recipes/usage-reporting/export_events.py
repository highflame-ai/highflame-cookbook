#!/usr/bin/env python3
"""Export Highflame Observatory events over the HTTP API.

Authentication is a two-step exchange:
  1. POST <auth-url>/oauth2/token with grant_type=api_key and a zid_sk_* key.
  2. Send the returned access_token as a bearer token to Observatory.

Observatory itself does not accept an API key. It accepts only a JWT that its
JWKS verifier accepts, so step 1 is mandatory.

Examples
--------
  export HIGHFLAME_API_KEY=zid_sk_...

  # Every event in the last 24 hours, as JSON Lines.
  ./export_events.py

  # Only prompts (drops tool calls), last 30 days, as CSV.
  ./export_events.py --prompts-only --since 30d --format csv -o prompts.csv

  # One user, blocked events only.
  ./export_events.py --user-id alice@example.com --decision deny

  # Explicit window against dev1.
  ./export_events.py \
      --start 2026-08-01T00:00:00Z --end 2026-08-28T00:00:00Z \
      --auth-url https://auth-dev.highflame.dev \
      --api-url https://api-dev.highflame.dev
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

DEFAULT_AUTH_URL = "https://auth.highflame.ai"
DEFAULT_API_URL = "https://api.highflame.ai"
EVENTS_PATH = "/v1/obs/events"
TOKEN_PATH = "/oauth2/token"

# Observatory emits a prompt turn as event_type=process_prompt with an empty
# tool_name. The same event_type carries tool calls when tool_name is set, so
# --prompts-only filters on the server AND drops the tool rows locally.
PROMPT_EVENT_TYPE = "process_prompt"

# Server-side page cap. The API defaults to 50 and rejects anything above 100
# with a 422 (see the `limit` maximum in /v1/obs/openapi.json.json).
MAX_PAGE_SIZE = 100
PAGE_SIZE = MAX_PAGE_SIZE

# Columns written by --format csv. Nested fields (scores, flags, labels) are
# omitted here — use --format jsonl to keep them.
# Claim names to try when reading the tenant scope out of the minted JWT,
# most specific first. AuthN issues account_id/project_id; the aliases cover
# an older or audience-scoped token shape.
ACCOUNT_CLAIMS = ("account_id", "accountId", "acct")
PROJECT_CLAIMS = ("project_id", "projectId", "proj")

CSV_COLUMNS = [
    "account_id",
    "project_id",
    "timestamp",
    "event_id",
    "trace_id",
    "session_id",
    "user_id",
    "user_name",
    "agent_id",
    "product",
    "service",
    "event_type",
    "event_subtype",
    "decision",
    "actual_decision",
    "mode",
    "highest_severity",
    "threat_count",
    "threat_categories",
    "policy_categories",
    "tool_name",
    "tool_category",
    "mcp_server_name",
    "mcp_tool_name",
    "model_provider",
    "model_name",
    "tokens_input",
    "tokens_output",
    "estimated_cost_usd",
    "duration_ms",
    "source_ide",
    "runtime",
    "workspace",
]


class ObservatoryError(RuntimeError):
    pass


def parse_since(value: str) -> timedelta:
    """Turn a duration like 90m, 24h, 30d into a timedelta."""
    match = re.fullmatch(r"(\d+)([mhd])", value.strip())
    if not match:
        raise argparse.ArgumentTypeError(
            f"invalid --since {value!r}; use a form like 90m, 24h, or 30d"
        )
    amount, unit = int(match.group(1)), match.group(2)
    return {"m": timedelta(minutes=amount),
            "h": timedelta(hours=amount),
            "d": timedelta(days=amount)}[unit]


def rfc3339(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def request_json(url: str, *, data: bytes | None = None,
                 headers: dict[str, str] | None = None,
                 method: str = "GET", timeout: int = 60) -> dict:
    """Issue one HTTP request and decode the JSON body.

    Retries a 429 or 5xx up to three times with a linear backoff. Raises
    ObservatoryError with the server's message on any other failure.
    """
    request = urllib.request.Request(url, data=data, method=method,
                                     headers=headers or {})
    last_error = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", "replace")[:500]
            if err.code in (429, 500, 502, 503, 504) and attempt < 2:
                last_error = f"HTTP {err.code}: {body}"
                time.sleep(2 * (attempt + 1))
                continue
            raise ObservatoryError(f"HTTP {err.code} from {url}: {body}") from err
        except urllib.error.URLError as err:
            if attempt < 2:
                last_error = str(err.reason)
                time.sleep(2 * (attempt + 1))
                continue
            raise ObservatoryError(f"cannot reach {url}: {err.reason}") from err
    raise ObservatoryError(f"gave up on {url}: {last_error}")


def decode_jwt_claims(token: str) -> dict:
    """Read the claim set out of a JWT without verifying the signature.

    Verification is the server's job — Observatory checks the signature
    against AuthN's JWKS on every call. This decode exists only to label the
    export with the tenant the token is scoped to, so a reader can tell which
    account and project the rows came from.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ObservatoryError("access_token is not a JWT; cannot read tenant scope")
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)  # restore base64 padding
    try:
        return json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as err:
        raise ObservatoryError(f"cannot decode JWT payload: {err}") from err


def read_tenant(claims: dict) -> tuple[str, str]:
    """Return (account_id, project_id) from a decoded claim set.

    An empty project_id is normal and meaningful: Observatory filters on
    `project_id = ?`, so an empty claim matches only rows stored with an empty
    project_id. It does NOT mean "every project".
    """
    def first(names):
        for name in names:
            value = claims.get(name)
            if value:
                return str(value)
        return ""

    return first(ACCOUNT_CLAIMS), first(PROJECT_CLAIMS)


def mint_token(auth_url: str, api_key: str) -> str:
    """Exchange a zid_sk_* API key for a bearer JWT."""
    payload = urllib.parse.urlencode({
        "grant_type": "api_key",
        "api_key": api_key,
    }).encode("utf-8")
    result = request_json(
        auth_url.rstrip("/") + TOKEN_PATH,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    token = result.get("access_token")
    if not token:
        raise ObservatoryError(f"token response carried no access_token: {result}")
    return token


def build_filters(args: argparse.Namespace) -> dict[str, str]:
    """Map CLI flags onto Observatory query parameters."""
    filters: dict[str, str] = {}
    optional = {
        "product": args.product,
        "service": args.service,
        "event_type": args.event_type,
        "decision": args.decision,
        "severity": args.severity,
        "threat_category": args.threat_category,
        "session_id": args.session_id,
        "user_id": args.user_id,
        "agent_id": args.agent_id,
        "source_ide": args.source_ide,
        "search": args.search,
    }
    for name, value in optional.items():
        if value:
            filters[name] = value
    if args.has_threats:
        filters["has_threats"] = "true"
    if args.prompts_only:
        # An explicit --event-type wins, so a caller can narrow further.
        filters.setdefault("event_type", PROMPT_EVENT_TYPE)
    return filters


def is_prompt(event: dict) -> bool:
    """True when the event is a prompt turn rather than a tool call."""
    return (event.get("event_type") == PROMPT_EVENT_TYPE
            and not event.get("tool_name")
            and not event.get("mcp_tool_name"))


def fetch_events(api_url: str, token: str, start: str, end: str,
                 filters: dict[str, str], *, prompts_only: bool,
                 max_events: int | None, page_size: int, verbose: bool):
    """Yield events page by page until the server runs out or the cap is hit."""
    base = api_url.rstrip("/") + EVENTS_PATH
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    page = 1
    emitted = 0
    while True:
        query = {"start": start, "end": end, "page": str(page),
                 "limit": str(page_size), **filters}
        url = f"{base}?{urllib.parse.urlencode(query)}"
        result = request_json(url, headers=headers)

        events = result.get("events") or []
        total = result.get("total", 0)
        if verbose:
            print(f"page {page}: {len(events)} events (total {total})",
                  file=sys.stderr)
        if not events:
            return

        for event in events:
            if prompts_only and not is_prompt(event):
                continue
            yield event
            emitted += 1
            if max_events and emitted >= max_events:
                return

        if page * page_size >= total:
            return
        page += 1


def label_tenant(events, account_id: str, project_id: str):
    """Prefix every event with the tenant the token is scoped to.

    The API does not return account_id or project_id on an event, so without
    this the export carries no evidence of its own scope. The server enforces
    the scope regardless — see tenantFilter in observatory's clickhouse repo,
    which pins `account_id = ? AND project_id = ?` from the JWT claims.
    """
    for event in events:
        yield {"account_id": account_id, "project_id": project_id, **event}


def write_jsonl(events, stream) -> int:
    count = 0
    for event in events:
        stream.write(json.dumps(event, separators=(",", ":")) + "\n")
        count += 1
    return count


def write_csv(events, stream, columns=None) -> int:
    writer = csv.DictWriter(stream, fieldnames=columns or CSV_COLUMNS,
                           extrasaction="ignore")
    writer.writeheader()
    count = 0
    for event in events:
        row = dict(event)
        # Flatten the list-valued columns so a spreadsheet can read them.
        for key in ("threat_categories", "policy_categories"):
            value = row.get(key)
            if isinstance(value, list):
                row[key] = ";".join(str(item) for item in value)
        writer.writerow(row)
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export Highflame Observatory events.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Examples")[-1],
    )
    parser.add_argument("--api-key", default=os.environ.get("HIGHFLAME_API_KEY"),
                        help="zid_sk_* key (default: $HIGHFLAME_API_KEY)")
    parser.add_argument("--auth-url", default=os.environ.get(
        "HIGHFLAME_AUTH_URL", DEFAULT_AUTH_URL))
    parser.add_argument("--api-url", default=os.environ.get(
        "HIGHFLAME_API_URL", DEFAULT_API_URL))

    window = parser.add_argument_group("time window")
    window.add_argument("--since", type=parse_since, default=parse_since("24h"),
                        help="relative window ending now, e.g. 90m, 24h, 30d "
                             "(default: 24h)")
    window.add_argument("--start", help="RFC3339 start; overrides --since")
    window.add_argument("--end", help="RFC3339 end (default: now)")

    filters = parser.add_argument_group("filters")
    filters.add_argument("--prompts-only", action="store_true",
                         help=f"only prompt turns (event_type="
                              f"{PROMPT_EVENT_TYPE} with no tool call)")
    filters.add_argument("--event-type", help="exact event_type; wins over "
                                              "--prompts-only for the server filter")
    filters.add_argument("--product")
    filters.add_argument("--service")
    filters.add_argument("--decision", help="allow, deny, monitor")
    filters.add_argument("--severity")
    filters.add_argument("--threat-category")
    filters.add_argument("--session-id")
    filters.add_argument("--user-id")
    filters.add_argument("--agent-id")
    filters.add_argument("--source-ide")
    filters.add_argument("--search", help="free-text search across the payload")
    filters.add_argument("--has-threats", action="store_true",
                         help="only events that carry at least one threat")

    output = parser.add_argument_group("output")
    output.add_argument("--format", choices=("jsonl", "csv"), default="jsonl")
    output.add_argument("-o", "--out", help="output file (default: stdout)")
    output.add_argument("--max", type=int, dest="max_events",
                        help="stop after this many events")
    output.add_argument("--page-size", type=int, default=PAGE_SIZE,
                        help=f"events per request, 1-{MAX_PAGE_SIZE} "
                             f"(default: {PAGE_SIZE})")
    output.add_argument("--no-tenant-columns", action="store_true",
                        help="omit the account_id/project_id columns and emit "
                             "the raw API shape")
    output.add_argument("-v", "--verbose", action="store_true",
                        help="report page progress on stderr")

    args = parser.parse_args()

    if not args.api_key:
        parser.error("no API key; pass --api-key or set HIGHFLAME_API_KEY")

    if not 1 <= args.page_size <= MAX_PAGE_SIZE:
        parser.error(f"--page-size must be between 1 and {MAX_PAGE_SIZE}; "
                     f"the API rejects anything larger with a 422")

    now = datetime.now(timezone.utc)
    end = args.end or rfc3339(now)
    start = args.start or rfc3339(now - args.since)

    try:
        token = mint_token(args.auth_url, args.api_key)
        claims = decode_jwt_claims(token)
        account_id, project_id = read_tenant(claims)
        if not account_id:
            # Naming the claims that ARE present turns a dead end into a
            # one-line fix: add the right name to ACCOUNT_CLAIMS.
            raise ObservatoryError(
                "the minted token carries no account_id claim, so the export "
                "cannot be labelled with its scope. Claims present: "
                + ", ".join(sorted(claims)))
        if args.verbose:
            print(f"token minted at {args.auth_url}", file=sys.stderr)
            print(f"scope: account_id={account_id} "
                  f"project_id={project_id or '(empty)'}", file=sys.stderr)

        events = fetch_events(
            args.api_url, token, start, end, build_filters(args),
            prompts_only=args.prompts_only,
            max_events=args.max_events,
            page_size=args.page_size,
            verbose=args.verbose,
        )
        if not args.no_tenant_columns:
            events = label_tenant(events, account_id, project_id)

        stream = open(args.out, "w", newline="") if args.out else sys.stdout
        try:
            if args.format == "csv":
                columns = (CSV_COLUMNS[2:] if args.no_tenant_columns
                           else CSV_COLUMNS)
                count = write_csv(events, stream, columns)
            else:
                count = write_jsonl(events, stream)
        finally:
            if args.out:
                stream.close()
    except ObservatoryError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130

    where = args.out or "stdout"
    print(f"wrote {count} events ({start} to {end}) to {where}", file=sys.stderr)
    print(f"scope: account_id={account_id} "
          f"project_id={project_id or '(empty)'} — one project only; a key "
          f"scoped elsewhere returns different rows", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
