#!/usr/bin/env python3
"""02 — Block a national ID (SSN), the way Tailscale Aperture calls Highflame.

Aperture fires a `pre_request` hook to Cerberus before forwarding the prompt;
Shield's `pii` detector flags the SSN and a Cedar forbid returns a block carrying
your branded message. This script sends the exact Aperture payload so you can see
the decision without standing up a tailnet.

Runs against PROD by default. Needs HIGHFLAME_API_KEY: the service key from
Studio -> Code Agents -> Tailscale Aperture.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is optional
    pass

ENDPOINT = os.environ.get(
    "HIGHFLAME_APERTURE_ENDPOINT",
    "https://api.highflame.ai/v1/cerberus/agent/events",
)
API_KEY = os.environ.get("HIGHFLAME_API_KEY")

# What a developer pastes when asking Claude to summarize customers.csv.
PROMPT = (
    "Summarize this customer row from customers.csv: "
    "name=Jane Doe, ssn=123-45-6789, plan=enterprise."
)


def aperture_pre_request(user_message: str) -> dict:
    """Build the Aperture `pre_request` hook payload (matches Cerberus' normalizer)."""
    return {
        "event": "pre_request",
        "metadata": {
            "login_name": "developer@example.com",
            "user_agent": "aperture_claude",
            "provider": "anthropic",
            "model": "claude-opus-4-8",
            "tailnet_name": "example.ts.net",
            "session_id": "demo-session",
            "request_id": "demo-request-02",
        },
        "user_message": user_message,
        "request_body": {
            "model": "claude-opus-4-8",
            "messages": [{"role": "user", "content": user_message}],
        },
    }


def post_event(payload: dict) -> dict:
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            try:
                return json.loads(r.read())
            except json.JSONDecodeError:
                return {"action": "error", "message": "invalid JSON response from server"}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"action": "error", "status_code": e.code, "message": body}
    except urllib.error.URLError as e:
        return {"action": "error", "message": f"network error: {e.reason}"}


def main() -> int:
    if not API_KEY:
        print("SKIP: HIGHFLAME_API_KEY not set (see .env.example).")
        return 2

    print(f"Aperture hook -> {ENDPOINT}\n")
    resp = post_event(aperture_pre_request(PROMPT))
    print(json.dumps(resp, indent=2))
    if resp.get("action") == "block":
        print(f"\nHighflame Security blocked the request -> {resp.get('message')!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
