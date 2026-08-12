#!/usr/bin/env python3
"""Shared helpers for the Exelixis PoV recipes.

Every recipe in this track proves a use case against a **live** Highflame tenant using two
primitives, and nothing else:

  1. `mint_token()` — exchange a ZeroID service key (`zid_sk_...`) for a short-lived access
     token at the AuthN token endpoint. The decoded claims of that token ARE the proof for
     the identity use cases (unique subject, 1-hour expiry, scopes, owner).
  2. `guard()` — send content to Shield's decision endpoint (`/v1/shield/guard`) with a
     Cedar action, and read back `allow` / `deny` / `modify` plus the determining policies.
     This is a *pre-execution* check: the caller decides based on the verdict before it ever
     forwards the request to a model or a tool.

Endpoints default to Highflame SaaS (prod). Point them at any environment (e.g. a dev
cluster) by setting the `HIGHFLAME_*_URL` variables in `.env`.

Nothing here verifies the JWT signature — `decode_claims()` is display-only, so you can see
exactly what the platform issued. Shield verifies the signature for real on every guard call.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv is an optional convenience
    pass

# --- Endpoints (prod SaaS defaults; override in .env for another environment) ----------
AUTHN_URL = os.environ.get("HIGHFLAME_AUTHN_URL", "https://auth.highflame.ai").rstrip(
    "/"
)
SHIELD_URL = os.environ.get("HIGHFLAME_SHIELD_URL", "https://api.highflame.ai").rstrip(
    "/"
)
GATEWAY_URL = os.environ.get(
    "HIGHFLAME_GATEWAY_URL", "https://gateway.highflame.ai"
).rstrip("/")

TOKEN_ENDPOINT = f"{AUTHN_URL}/oauth2/token"
REVOKE_ENDPOINT = f"{AUTHN_URL}/oauth2/token/revoke"
GUARD_ENDPOINT = f"{SHIELD_URL}/v1/shield/guard"

API_KEY = os.environ.get("HIGHFLAME_API_KEY")

TIMEOUT = float(os.environ.get("HIGHFLAME_HTTP_TIMEOUT", "30"))


class HighflameError(RuntimeError):
    """A non-2xx response we could not interpret as an expected decision."""


def _post(url: str, body: dict, *, bearer: str | None = None) -> tuple[int, dict]:
    """POST JSON, return (status_code, parsed_body). A JSON error body is parsed, not raised."""
    headers = {"Content-Type": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, _read_json(r.read())
    except urllib.error.HTTPError as e:
        return e.code, _read_json(e.read())
    except urllib.error.URLError as e:
        raise HighflameError(f"network error contacting {url}: {e.reason}") from e


def _post_form(url: str, fields: dict) -> tuple[int, dict]:
    """POST application/x-www-form-urlencoded (RFC 6749/7009 use form bodies, not JSON)."""
    data = urllib.parse.urlencode(fields).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, _read_json(r.read())
    except urllib.error.HTTPError as e:
        return e.code, _read_json(e.read())
    except urllib.error.URLError as e:
        raise HighflameError(f"network error contacting {url}: {e.reason}") from e


def _read_json(raw: bytes) -> dict:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"_raw": raw.decode(errors="replace")}


# --- Identity -------------------------------------------------------------------------
def mint_token(api_key: str | None = None, *, scope: str | None = None) -> dict:
    """Exchange a `zid_sk_...` service key for a short-lived access token.

    Returns the full token response: `access_token`, `token_type`, `expires_in`, `scope`.
    Pass `scope` to request least privilege (e.g. "mcp:read"); omit it to receive the
    identity's full ceiling.
    """
    key = api_key or API_KEY
    if not key:
        raise HighflameError("no API key: set HIGHFLAME_API_KEY (see .env.example)")
    body: dict = {"grant_type": "api_key", "api_key": key}
    if scope:
        body["scope"] = scope
    status, resp = _post(TOKEN_ENDPOINT, body)
    if status != 200 or "access_token" not in resp:
        raise HighflameError(f"token mint failed ({status}): {resp}")
    return resp


def decode_claims(access_token: str) -> dict:
    """Base64url-decode a JWT payload for DISPLAY (no signature verification)."""
    try:
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)  # pad to a multiple of 4
        return json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError) as e:
        raise HighflameError(f"could not decode token payload: {e}") from e


def revoke_token(access_token: str) -> int:
    """Revoke a token (RFC 7009 — form-encoded). Returns the HTTP status (200 on success)."""
    status, _ = _post_form(REVOKE_ENDPOINT, {"token": access_token})
    return status


# --- Enforcement ----------------------------------------------------------------------
def guard(
    access_token: str,
    content: str,
    *,
    action: str = "process_prompt",
    content_type: str = "prompt",
    mode: str = "enforce",
    session_id: str | None = None,
    request_id: str | None = None,
    tool: dict | None = None,
) -> dict:
    """Ask Shield to evaluate `content` against active Cedar policy BEFORE the caller acts.

    - `action`: the Cedar action — process_prompt | call_tool | read_file | write_file | connect_server.
    - `content_type`: prompt | response | tool_call — lets one policy cover the request side,
      the model-output side, and tool results.
    - `mode`: enforce (deny is returned) or monitor (records a would-block; the real verdict
      shows up as `actual_decision`).
    Returns the parsed decision. `decision_of(resp)` collapses monitor/enforce to the real verdict.
    """
    body: dict = {
        "content": content,
        "content_type": content_type,
        "action": action,
        "mode": mode,
    }
    if session_id:
        body["session_id"] = session_id
    if request_id:
        body["request_id"] = request_id
    if tool:
        body["tool"] = tool
    status, resp = _post(GUARD_ENDPOINT, body, bearer=access_token)
    if status == 401:
        # A revoked/expired token is itself a decision worth surfacing.
        return {"decision": "unauthorized", "status_code": 401, "_body": resp}
    if status not in (200, 403):
        raise HighflameError(f"guard failed ({status}): {resp}")
    return resp


def decision_of(resp: dict) -> str:
    """The real verdict, collapsing monitor mode: `actual_decision` wins when present."""
    return resp.get("actual_decision") or resp.get("decision") or "unknown"


def determining_policies(resp: dict) -> list[dict]:
    return resp.get("determining_policies") or resp.get("determining_policy") or []


# --- CLI ergonomics -------------------------------------------------------------------
def require_key() -> str | None:
    """Return the API key, or None after printing a SKIP line (caller should `return 2`)."""
    if not API_KEY:
        print("SKIP: HIGHFLAME_API_KEY not set (see .env.example).")
        return None
    return API_KEY


def show(resp: dict, *, label: str = "decision") -> None:
    verdict = decision_of(resp)
    print(f"  {label}: {verdict}", end="")
    pols = determining_policies(resp)
    if pols:
        names = ", ".join(
            p.get("rule_id") or p.get("policy_name") or "?" for p in pols[:3]
        )
        print(f"  (policy: {names})", end="")
    msg = resp.get("reject_message") or resp.get("message")
    if msg and verdict in ("deny", "unauthorized"):
        print(f'  -> "{msg}"', end="")
    print()


def banner(title: str) -> None:
    print(f"\n{'=' * 4} {title} {'=' * max(4, 72 - len(title))}")
