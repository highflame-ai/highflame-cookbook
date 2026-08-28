#!/usr/bin/env python3
"""RFC 9470 challenge-retry for AARM STEP_UP — the CIBA poll, made visible.

When a guarded call matches a policy carrying @step_up_required("<role>"),
Shield answers with `decision: step_up` and an RFC 9470 challenge:

    401 Unauthorized
    WWW-Authenticate: Bearer error="insufficient_user_authentication",
                      acr_values="urn:highflame:aarm:step_up"
    { "auth_req_id": ..., "interval": 5, "expires_in": 300,
      "binding_message": "Block 203.0.113.7 at the edge firewall — ...",
      "authorization_details": [...] }

The agent's own code never sees CIBA — this module is the SDK-layer dance:
poll AuthN's /oauth2/token with the CIBA grant until the approver resolves in
Studio's approval pane, then hand back the upgraded token (which carries the
granted authorization_details claim) so the caller retries the guarded call.

Newer highflame SDK releases ship this as built-in middleware; the recipe
implements it inline anyway, because watching the poll print
`authorization_pending ... approved` IS the demo. Timeout is fail-closed:
when `expires_in` lapses server-side, the token poll returns `expired_token`
and the action stays denied.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

CIBA_GRANT = "urn:openid:params:grant-type:ciba"


@dataclass
class StepUpChallenge:
    auth_req_id: str
    interval: int
    expires_in: int
    binding_message: str

    @classmethod
    def from_response(cls, body: dict) -> "StepUpChallenge":
        return cls(
            auth_req_id=body["auth_req_id"],
            interval=int(body.get("interval", 5)),
            expires_in=int(body.get("expires_in", 300)),
            binding_message=body.get("binding_message", ""),
        )


@dataclass
class StepUpResult:
    outcome: str  # "approved" | "denied" | "expired" | "error"
    access_token: str = ""
    detail: str = ""


def await_step_up(challenge: StepUpChallenge, client_id: str = "") -> StepUpResult:
    """Poll the CIBA token grant until the approver resolves, fail-closed."""
    token_url = os.environ.get("HIGHFLAME_TOKEN_URL", "https://auth.highflame.ai/oauth2/token")
    ceiling = min(challenge.expires_in,
                  int(os.environ.get("STEP_UP_WAIT_SECONDS", "300")))
    deadline = time.monotonic() + ceiling

    print(f"  [step-up] approval requested: {challenge.binding_message!r}")
    print(f"  [step-up] waiting on the soc_lead approval pane in Studio "
          f"(auth_req_id={challenge.auth_req_id}, up to {ceiling}s)")

    with httpx.Client(timeout=15) as http:
        while time.monotonic() < deadline:
            data = {"grant_type": CIBA_GRANT, "auth_req_id": challenge.auth_req_id}
            if client_id:
                data["client_id"] = client_id
            try:
                resp = http.post(token_url, data=data)
            except httpx.HTTPError as exc:
                return StepUpResult("error", detail=f"token endpoint unreachable: {exc}")

            if resp.status_code == 200:
                print("  [step-up] APPROVED — upgraded token carries authorization_details")
                return StepUpResult("approved", access_token=resp.json()["access_token"])

            err = (resp.json().get("error", "") if "json" in resp.headers.get("content-type", "")
                   else resp.text[:120])
            if err == "authorization_pending":
                print("  [step-up] pending...")
                time.sleep(challenge.interval)
                continue
            if err == "slow_down":
                challenge.interval += 5
                time.sleep(challenge.interval)
                continue
            if err == "access_denied":
                print("  [step-up] DENIED by the approver — action stays refused")
                return StepUpResult("denied")
            if err == "expired_token":
                print("  [step-up] EXPIRED with no resolution — fail-closed deny")
                return StepUpResult("expired")
            return StepUpResult("error", detail=f"[{resp.status_code}] {err}")

    print("  [step-up] local wait ceiling reached — treating as fail-closed deny")
    return StepUpResult("expired")
