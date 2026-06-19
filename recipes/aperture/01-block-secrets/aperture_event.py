#!/usr/bin/env python3
"""01 — Block a credential leak, exactly the way Tailscale Aperture calls Highflame.

When a developer's Claude Code runs behind Tailscale Aperture in your tailnet, Aperture
fires a `pre_request` hook to Highflame **before** forwarding the prompt to the model.
Cerberus normalizes the Aperture payload, runs Shield, and returns:

    {"action": "allow"}
    {"action": "block", "status_code": 403, "message": "<branded policy reason>"}

This script sends the *exact* `pre_request` payload Aperture would send (see
highflame-cerberus/integration/aperture.md), so you can see Highflame's decision — and
the branded block message — without standing up a tailnet.

Runs against PROD by default. Needs HIGHFLAME_API_KEY: the service key you generate in
Studio -> Code Agents -> Tailscale Aperture (the same key you paste into Aperture's hook).
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

# What a developer pastes from the demo-vault's deploy.sh. The credentials are AWS's own
# documented example values — they trip the secret detector without being real keys.
LEAK = (
    "Help me debug this deploy script — it exports "
    "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE and "
    "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY before terraform apply."
)


def aperture_pre_request(user_message: str) -> dict:
    """Build the Aperture `pre_request` hook payload (matches Cerberus' normalizer)."""
    return {
        "event": "pre_request",
        "metadata": {
            "login_name": "developer@example.com",  # Tailscale identity rides along
            "user_agent": "aperture_claude",  # Claude Code behind Aperture
            "provider": "anthropic",
            "model": "claude-opus-4-8",
            "tailnet_name": "example.ts.net",
            "session_id": "demo-session",
            "request_id": "demo-request-01",
        },
        "user_message": user_message,
        "request_body": {
            "model": "claude-opus-4-8",
            "messages": [{"role": "user", "content": user_message}],
        },
    }


def post_event(payload: dict) -> dict:
    """POST a hook event to Cerberus and return the parsed guardrail response."""
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:  # block may arrive as a non-2xx with a JSON body
        body = e.read().decode()
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"action": "error", "status_code": e.code, "message": body}


def main() -> int:
    if not API_KEY:
        print("SKIP: HIGHFLAME_API_KEY not set (see .env.example).")
        return 2

    print(f"Aperture hook -> {ENDPOINT}\n")
    resp = post_event(aperture_pre_request(LEAK))
    print(json.dumps(resp, indent=2))
    if resp.get("action") == "block":
        print(f"\nHighflame Security blocked the request -> {resp.get('message')!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
