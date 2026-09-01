#!/usr/bin/env python3
"""A minimal ODIS-conformant agent — the shape to copy into your own codebase.

This is the whole pattern in one file: an orchestrator with a narrow credential,
a sub-agent it delegates a *subset* of its authority to, and a governance
checkpoint consulted before every action. Roughly 60 lines of actual logic.

    python secure_agent.py

What to take from it, in order of importance:

1. The agent never holds a long-lived credential in memory. It holds a bootstrap
   key (from your secret store) and exchanges it for a short-lived one.
2. Authority is declared at registration and can only narrow from there. The
   sub-agent is registered for less than the orchestrator, so a bug — or a
   prompt injection — in the orchestrator cannot hand it more.
3. Every action goes through the checkpoint *before* it happens, and the
   checkpoint sees who is asking, not just what is being asked.
4. Revocation is a governance operation you can perform at any time, and it
   takes effect at the enforcement point, not at token expiry.
"""

from __future__ import annotations

import sys

from odis_client import (
    Agent,
    ODISRecipeError,
    delegate,
    guard,
    load_config,
    new_holder_keypair,
    unique,
    verify_local,
)


def main() -> int:
    cfg = load_config()
    if not cfg.can_provision:
        print(
            "SKIP: needs HIGHFLAME_REGISTRAR_TOKEN or "
            "HIGHFLAME_INTERNAL_SERVICE_SECRET — see .env.example",
            file=sys.stderr,
        )
        return 2
    cp = cfg.control_plane()
    try:
        return _run(cfg, cp)
    finally:
        # ------------------------------------------------------------- Retire
        # The last lifecycle stage, and the one most rollouts forget. An agent
        # that finished its job should stop being able to act — retirement
        # deactivates the identity and revokes its credentials, keeping the
        # record for audit.
        #
        # This is a `finally` on purpose: a run that dies halfway has still
        # created live agents, and that is exactly when you least want them
        # left behind.
        print("\nRetiring the agents this run created")
        retired, failed = cp.retire_all_created()
        print(f"  {retired} retired" + (f", {failed} failed" if failed else ""))


def _run(cfg, cp) -> int:
    # ---------------------------------------------------------------- Layer 1
    # Registration is a one-time governance act, normally done by your platform
    # team or a provisioning pipeline — not by the agent at every boot. What the
    # agent boots with is the bootstrap key, from your secret store.
    print("Layer 1 — registering the orchestrator")
    orch_scopes = ["tools:read", "tools:execute"]
    orch_record, orch_key = cp.provision(
        external_id=unique("research-orchestrator"),
        owner_user_id=cfg.owner_user_id,
        scopes=orch_scopes,
        trust_level="first_party",
        framework="python-sdk",
        publisher="your-team",
    )
    orchestrator = Agent(
        authn_url=cfg.authn_url,
        bootstrap_key=orch_key,
        wimse_uri=orch_record["wimse_uri"],
        identity_id=orch_record["id"],
    )
    print(f"  identity : {orchestrator.wimse_uri}")
    print(f"  owner    : {orch_record['owner_user_id']}")
    print(f"  authority: {orch_record.get('allowed_scopes') or orch_scopes}")

    # The sub-agent gets a holder key, because delegation requires it to *prove*
    # it holds the private half — a stolen credential alone is not enough.
    sub_private, sub_public = new_holder_keypair()
    sub_scopes = ["tools:read"]
    sub_record, sub_key = cp.provision(
        external_id=unique("summariser"),
        owner_user_id=cfg.owner_user_id,
        scopes=sub_scopes,  # strictly less than the orchestrator
        trust_level="first_party",
        public_key_pem=sub_public,
    )
    sub_agent = Agent(
        authn_url=cfg.authn_url,
        bootstrap_key=sub_key,
        wimse_uri=sub_record["wimse_uri"],
        identity_id=sub_record["id"],
        holder_private_key=sub_private,
    )
    print(f"\n  sub-agent: {sub_agent.wimse_uri}")
    print(f"  authority: {sub_record.get('allowed_scopes') or sub_scopes}  (narrower by design)")

    # The runtime credential. Short-lived; re-exchanged on expiry.
    credential = orchestrator.token()
    claims = verify_local(cfg.authn_url, credential["access_token"])
    print(
        f"\n  credential: ttl={int(claims['exp']) - int(claims['iat'])}s "
        f"scopes={claims.get('scopes')} jti={claims['jti'][:8]}"
    )

    # ---------------------------------------------------------------- Layer 2
    # Delegation. The orchestrator hands down read access only — note it does
    # NOT pass tools:execute, and could not even if it tried, because the
    # sub-agent is not registered for it.
    print("\nLayer 2 — delegating a subset of authority")
    issuer = claims["iss"]
    delegated = delegate(
        cfg.authn_url,
        subject_token=credential["access_token"],
        actor_assertion=sub_agent.holder_assertion(audience=issuer),
        scope="tools:read",
    )
    dc = verify_local(cfg.authn_url, delegated["access_token"])
    print(f"  acting as : {dc['sub']}")
    print(f"  on behalf : {(dc.get('act') or {}).get('sub')}")
    print(f"  depth     : {dc.get('delegation_depth')}  scopes: {dc.get('scopes')}")

    try:
        delegate(
            cfg.authn_url,
            subject_token=credential["access_token"],
            actor_assertion=sub_agent.holder_assertion(audience=issuer),
            scope="tools:execute",
        )
        print("  escalation: ACCEPTED — investigate, this should not happen")
    except ODISRecipeError:
        print("  escalation: refused (sub-agent is not registered for tools:execute)")

    # ---------------------------------------------------------------- Layer 3
    # Every action is checked before it runs, with the acting credential — so
    # the decision is made about *this* principal, not about your service.
    print("\nLayer 3 — checking each action at the governance checkpoint")
    actions = [
        ("orchestrator", credential["access_token"], "call_tool", "run the deploy script"),
        ("sub-agent", delegated["access_token"], "process_prompt", "summarise this document"),
        ("sub-agent", delegated["access_token"], "call_tool", "run the deploy script"),
    ]
    for who, token, action, content in actions:
        out = guard(cfg.shield_url, token, content=content, action=action)
        if out.no_policies:
            verdict = "fail-closed (no policies enabled in this tenant)"
        elif out.decision:
            verdict = f"{out.decision}" + (f" — {out.reason}" if out.reason else "")
        else:
            verdict = f"HTTP {out.status}"
        print(f"  {who:13s} {action:15s} -> {verdict}")

    # ---------------------------------------------------------- Layer 3 (cont.)
    # Revocation. One call, and the credential stops working at the checkpoint —
    # you do not wait for it to expire.
    print("\nLayer 3 — revoking the sub-agent's delegated credential")
    cp.revoke_credential(
        identity_id=sub_agent.identity_id,
        jti=dc["jti"],
        reason="task complete",
    )
    after = guard(
        cfg.shield_url, delegated["access_token"], content="anything", action="process_prompt"
    )
    print(
        f"  checkpoint now returns HTTP {after.status}"
        f"{' (rejected)' if after.status == 401 else ''}"
    )

    print("\nDone. The pattern above is the whole recipe — see README.md for why "
          "each step is where it is.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ODISRecipeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
