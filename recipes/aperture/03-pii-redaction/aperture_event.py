#!/usr/bin/env python3
"""03 — Redact PII (email) transparently, via Tailscale Aperture's `modify` action.

When a developer's prompt contains an email, a Shield redaction policy scrubs it and
Cerberus returns Aperture's `modify` action with a rewritten `request_body` — Aperture
forwards the *scrubbed* prompt to the model. The developer stays productive; the address
never reaches the provider. (Implemented by the Cerberus modify exposure; the Aperture
guardrail `modify` action carries the replacement body.)

This script sends the exact Aperture `pre_request` payload and prints what Highflame
returns — including the scrubbed prompt Aperture will forward.

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
# The developer this request is attributed to. Aperture supplies a verified
# login_name in production; here it is configurable so you can run the script as
# yourself. With Highflame's identity gate enabled, this MUST be a member of your
# Highflame org under this email (same email as your Tailscale login) — a
# non-member is denied at the identity layer before any content policy runs.
LOGIN_NAME = os.environ.get("HIGHFLAME_APERTURE_LOGIN") or "developer@example.com"

EMAIL = "jane.doe@example.com"
PROMPT = (
    f"Draft a short follow-up email to our new lead. Their address is {EMAIL} "
    "— keep it under 80 words."
)


def aperture_pre_request(user_message: str) -> dict:
    """Build the Aperture `pre_request` hook payload (matches Cerberus' normalizer)."""
    return {
        "event": "pre_request",
        "metadata": {
            "login_name": LOGIN_NAME,
            "user_agent": "aperture_claude",
            "provider": "anthropic",
            "model": "claude-opus-4-8",
            "tailnet_name": "example.ts.net",
            "session_id": "demo-session",
            "request_id": "demo-request-03",
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


def forwarded_prompt(resp: dict) -> str | None:
    """Pull the (scrubbed) user message Aperture would forward from a modify response."""
    for msg in (resp.get("request_body") or {}).get("messages", []):
        if msg.get("role") == "user":
            return msg.get("content")
    return None


def main() -> int:
    if not API_KEY:
        print("SKIP: HIGHFLAME_API_KEY not set (see .env.example).")
        return 2

    print(f"Aperture hook -> {ENDPOINT}\n")
    resp = post_event(aperture_pre_request(PROMPT))
    print(json.dumps(resp, indent=2))

    action = resp.get("action")
    if action == "modify":
        print(f"\nHighflame redacted the prompt; Aperture forwards -> {forwarded_prompt(resp)!r}")
    elif action == "block":
        print(f"\nHighflame blocked it -> {resp.get('message')!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
