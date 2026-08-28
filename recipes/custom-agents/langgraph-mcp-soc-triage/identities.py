#!/usr/bin/env python3
"""Per-agent identity bootstrap — the delegation-chain half of the demo.

Four agents, two delegation paths, on purpose (this mirrors the platform's own
decision table for orchestrator-spawned workloads):

  supervisor    RFC 8693 token exchange over the analyst's token
                -> act.sub carries the human analyst
  log-collector Path C': api_key grant, created_by=supervisor,
                scopes attenuated to tools:logs:read
  threat-analyst  Path C': same, scopes tools:intel:read
  responder     Path C: RFC 8693 WITH actor_token — it takes the one
                privileged action, so it proves its own identity;
                act.sub chain rides in the token itself

The read-only workers are ephemeral subprocess-shaped workloads, so the cheap
api_key + created_by pattern is the *correct* one for them — full RFC 8693 on
every in-process node is overhead the architecture explicitly rejects. The
responder is the contrast: cryptographic chain, because write authority.

Every identity resolves to a WIMSE URI:
  spiffe://highflame.io/{account}/{project}/agent/{external_id}
and the run prints the URI (and act chain, where present) at each hop.

Fallback behaviour: this is a cookbook recipe, and tenants differ in which
identity capabilities are enabled (actor-assertion key enrollment after
registration is CAP-IDN-012, still `planned`). Every mint below therefore
degrades gracefully: if a flow is unavailable, the agent runs on the bootstrap
service-key identity and the run says so loudly — the guard beats still work,
the delegation printout marks itself DEGRADED.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field

import httpx

TOKEN_EXCHANGE_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"

AGENT_SCOPES = {
    "soc-supervisor": ["triage:read", "triage:route", "tools:logs:read", "tools:intel:read"],
    "log-collector": ["tools:logs:read"],
    "threat-analyst": ["tools:intel:read"],
    "responder": ["tools:firewall:write"],
}


@dataclass
class AgentIdentity:
    name: str
    token: str
    scopes: list[str]
    wimse_uri: str = ""
    act_chain: list[str] = field(default_factory=list)
    degraded: bool = False

    def describe(self) -> str:
        chain = " -> ".join(self.act_chain) if self.act_chain else "(created_by metadata)"
        tag = "  [DEGRADED: bootstrap key]" if self.degraded else ""
        return f"{self.name}: {self.wimse_uri or '(no WIMSE URI)'} | chain: {chain}{tag}"


def _claims(token: str) -> dict:
    """Decode a JWT payload without verifying — display only, never trust."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def _act_chain(claims: dict) -> list[str]:
    """Flatten the nested RFC 8693 act claim into an ordered list of subs."""
    chain, act = [], claims.get("act")
    while isinstance(act, dict):
        chain.append(act.get("sub", "?"))
        act = act.get("act")
    return chain


class IdentityBroker:
    """Mints per-agent tokens from AuthN; falls back to the bootstrap key."""

    def __init__(self) -> None:
        self.bootstrap_key = os.environ["HIGHFLAME_API_KEY"]
        # Derive the token endpoint from HIGHFLAME_TOKEN_URL when set, so the
        # broker always talks to the same auth host as the SDK client. A dev
        # key against the SaaS host fails as "invalid api key", which reads
        # like a bad key rather than a wrong environment.
        self.token_url = os.environ.get(
            "HIGHFLAME_TOKEN_URL",
            os.environ.get("HIGHFLAME_AUTHN_URL", "https://auth.highflame.ai").rstrip("/")
            + "/oauth2/token",
        )
        self.analyst_token = os.environ.get("HIGHFLAME_ANALYST_TOKEN", "")
        self._http = httpx.Client(timeout=15)

    # -- token flows --------------------------------------------------------

    def _token_post(self, data: dict) -> dict | None:
        try:
            # JSON body — the wire shape AuthN's token endpoint accepts (and
            # the one the SDK's own TokenManager uses).
            resp = self._http.post(self.token_url, json=data)
        except httpx.HTTPError as exc:
            print(f"  WARN AuthN unreachable ({exc.__class__.__name__}); falling back.")
            return None
        if resp.status_code != 200:
            return {"_error": resp.status_code, "_body": resp.text[:300]}
        return resp.json()

    def _fallback(self, name: str) -> AgentIdentity:
        print(f"  WARN {name}: running on the bootstrap service-key identity.")
        return AgentIdentity(name=name, token=self.bootstrap_key,
                             scopes=AGENT_SCOPES[name], degraded=True)

    def mint_supervisor(self) -> AgentIdentity:
        """RFC 8693 exchange over the analyst's token, so act.sub = the human."""
        name = "soc-supervisor"
        if not self.analyst_token:
            print("  NOTE no HIGHFLAME_ANALYST_TOKEN set — the human hop of the chain "
                  "is skipped (set it to see act.sub carry the analyst).")
            return self._fallback(name)
        granted = self._token_post({
            "grant_type": TOKEN_EXCHANGE_GRANT,
            "subject_token": self.analyst_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "scope": " ".join(AGENT_SCOPES[name]),
        })
        if not granted or "_error" in granted:
            if granted:
                print(f"  WARN supervisor exchange failed [{granted['_error']}] {granted['_body']}")
            return self._fallback(name)
        return self._from_token(name, granted["access_token"])

    def mint_worker(self, name: str, supervisor: AgentIdentity) -> AgentIdentity:
        """Path C': api_key grant with attenuated scopes; chain via created_by."""
        granted = self._token_post({
            "grant_type": "api_key",
            "api_key": self.bootstrap_key,
            "scope": " ".join(AGENT_SCOPES[name]),
            # created_by ties the ephemeral worker to its orchestrator in
            # ZeroID; the chain is registry metadata here, not an act claim.
            "created_by": supervisor.wimse_uri or "soc-supervisor",
        })
        if not granted or "_error" in granted:
            if granted:
                print(f"  WARN {name} api_key grant failed [{granted['_error']}] {granted['_body']}")
            return self._fallback(name)
        return self._from_token(name, granted["access_token"])

    def mint_responder(self, supervisor: AgentIdentity) -> AgentIdentity:
        """Path C: full RFC 8693 with actor_token — the cryptographic chain.

        The actor assertion requires the responder's signing key to be
        registered up front (post-registration enrollment is CAP-IDN-012,
        still planned). A tenant without that setup degrades gracefully.
        """
        name = "responder"
        actor_assertion = os.environ.get("HIGHFLAME_RESPONDER_ASSERTION", "")
        if supervisor.degraded or not actor_assertion:
            if not actor_assertion:
                print("  NOTE no HIGHFLAME_RESPONDER_ASSERTION set — responder runs "
                      "without the act.sub chain (see README, 'Registering the responder').")
            return self._fallback(name)
        granted = self._token_post({
            "grant_type": TOKEN_EXCHANGE_GRANT,
            "subject_token": supervisor.token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "actor_token": actor_assertion,
            "actor_token_type": "urn:ietf:params:oauth:token-type:jwt",
            "scope": " ".join(AGENT_SCOPES[name]),
        })
        if not granted or "_error" in granted:
            if granted:
                print(f"  WARN responder exchange failed [{granted['_error']}] {granted['_body']}")
            return self._fallback(name)
        return self._from_token(name, granted["access_token"])

    def attempt_scope_widening(self, worker: AgentIdentity) -> tuple[bool, str]:
        """The issuance-time deny beat: the analyst asks for the firewall scope.

        Expected: AuthN refuses (triple intersection — requested ∩ delegator ∩
        allowed — never widens). Returns (was_refused, detail).
        """
        granted = self._token_post({
            "grant_type": TOKEN_EXCHANGE_GRANT,
            "subject_token": worker.token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "scope": "tools:firewall:write",
        })
        if granted is None:
            return False, "AuthN unreachable — beat skipped"
        if "_error" in granted:
            return True, f"refused at issuance [{granted['_error']}] {granted['_body']}"
        got = granted.get("scope", "")
        if "tools:firewall:write" not in got:
            return True, f"token minted but scope silently narrowed to {got!r}"
        return False, "AuthN granted the widened scope — check tenant scope config"

    # -- helpers ------------------------------------------------------------

    def _from_token(self, name: str, token: str) -> AgentIdentity:
        claims = _claims(token)
        return AgentIdentity(
            name=name, token=token, scopes=AGENT_SCOPES[name],
            wimse_uri=claims.get("sub", ""), act_chain=_act_chain(claims),
        )


def bootstrap() -> dict[str, AgentIdentity]:
    """Mint the full cast and print the chain evidence."""
    broker = IdentityBroker()
    print("[identity] minting the cast")
    supervisor = broker.mint_supervisor()
    cast = {
        "soc-supervisor": supervisor,
        "log-collector": broker.mint_worker("log-collector", supervisor),
        "threat-analyst": broker.mint_worker("threat-analyst", supervisor),
        "responder": broker.mint_responder(supervisor),
    }
    for ident in cast.values():
        print(f"  {ident.describe()}")
    print()
    return cast


if __name__ == "__main__":
    bootstrap()
