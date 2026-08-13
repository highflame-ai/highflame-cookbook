#!/usr/bin/env python3
"""CI smoke test for the Overwatch gateway-mode recipe, against live prod/SaaS.

Both supported agents depend on the same wiring: a Highflame gateway key that the
gateway accepts, reachable on the path shape that agent's client uses. Claude Code
appends `/v1/messages` to the configured URL; Codex appends `/responses` to a URL
that already ends in `/v1`. This asserts the gateway authenticates the key on both,
so a failure here explains an agent failing before anyone edits agent config.

An upstream error (no provider configured for the tenant, an expired provider key,
a rate limit) is a PASS: it means the gateway authenticated us and forwarded the
request. Only the gateway's own rejection is a failure.

Exit codes: 0 = pass, 1 = assertion failed, 2 = missing config (skipped, not failed).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_GATEWAY = "https://gateway.highflame.ai/llm"
TIMEOUT_S = 45

# The gateway's own rejection, as distinct from anything upstream says.
GATEWAY_REJECTION_MARKERS = (
    "Authentication required",
    "invalid_credential",
    "tenant_unresolved",
)


def post(url: str, key: str, payload: dict) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-highflame-apikey": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return response.status, response.read().decode()[:400]
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()[:400]


def check(label: str, url: str, key: str, payload: dict) -> bool:
    try:
        status, body = post(url, key, payload)
    except Exception as exc:  # noqa: BLE001 — network/TLS: cannot conclude
        print(f"FAIL {label}: could not reach the gateway ({exc})")
        return False

    if status == 401 and any(m in body for m in GATEWAY_REJECTION_MARKERS):
        print(f"FAIL {label}: the gateway rejected this key (HTTP 401)")
        return False

    if status in (401, 403):
        # Someone upstream refused, which still proves our key got us through.
        print(f"PASS {label}: gateway accepted the key (provider returned {status})")
        return True

    if status == 429:
        print(f"PASS {label}: gateway accepted the key and applied your rate limit (429)")
        return True

    if status == 404:
        print(f"FAIL {label}: no route at {url} — check the configured gateway URL")
        return False

    print(f"PASS {label}: gateway responded {status}")
    return True


def main() -> int:
    key = os.environ.get("HIGHFLAME_GATEWAY_KEY") or os.environ.get("HIGHFLAME_API_KEY")
    if not key:
        print("SKIP: HIGHFLAME_GATEWAY_KEY not set.")
        return 2

    base = os.environ.get("HIGHFLAME_GATEWAY_URL", DEFAULT_GATEWAY).rstrip("/")
    print(f"Gateway: {base}")

    ok = check(
        "Claude Code path (/v1/messages)",
        f"{base}/v1/messages",
        key,
        {
            "model": "claude-sonnet-4",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}],
        },
    )

    # Codex is configured with a base URL that already ends in /v1, and appends
    # only /responses, so the effective path is the same shape asserted here.
    ok = (
        check(
            "Codex path (/v1/responses)",
            f"{base}/v1/responses",
            key,
            {"model": "gpt-5", "input": "ping", "max_output_tokens": 16},
        )
        and ok
    )

    if not ok:
        print(
            "\nOne or both paths failed. Fix this before changing agent configuration: "
            "an agent pointed at a gateway that will not authenticate it cannot reach a model."
        )
        return 1

    print("\nBoth path shapes authenticate. Agents configured against this URL will route.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
