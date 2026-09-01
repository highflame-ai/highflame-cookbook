import marimo

__generated_with = "0.9.0"
app = marimo.App(width="medium", app_title="ODIS — the three layers, live")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md(
        r"""
        # ODIS — the three layers, live

        [ODIS](https://github.com/cosai-oasis/ws4-odis/blob/main/RFCs/ODIS.md)
        (CoSAI WS4) specifies how an agent gets an identity, how it receives
        authority from a human, and how that authority is governed at the point
        of use. Three layers:

        | Layer | The question it answers |
        | --- | --- |
        | **1 — The Passport** | *What* software is running, and *which instance* is asking? |
        | **2 — The Bridge** | *Who* is this agent acting for, and with how much of their authority? |
        | **3 — The Router** | *What* may this specific request do, right now? |

        Every cell below makes a **real call**. Nothing is mocked, and nothing
        is asserted from documentation.

        ```
        pip install -r requirements.txt
        cp .env.example .env
        marimo run walkthrough.py
        ```
        """
    )
    return


@app.cell
def _(mo):
    mo.md("## 0. Connect")
    return


@app.cell
def _(mo):
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

    cfg = load_config()
    ready = cfg.can_provision

    mo.md(
        f"""
        | Setting | Value |
        | --- | --- |
        | Identity plane (L1 + L2) | `{cfg.authn_url}` |
        | Checkpoint (L3) | `{cfg.shield_url}` |
        | Tenant | `{cfg.account_id}` / `{cfg.project_id}` |
        | Accountable owner | `{cfg.owner_user_id}` |
        | Provisioning credential | {"registrar token" if cfg.registrar_token else ("internal secret" if cfg.internal_secret else "**missing — see .env.example**")} |
        """
    )
    return (
        Agent,
        ODISRecipeError,
        cfg,
        delegate,
        guard,
        load_config,
        new_holder_keypair,
        ready,
        unique,
        verify_local,
    )


@app.cell
def _(cfg, mo, ready):
    cp = cfg.control_plane() if ready else None
    mo.md(
        f"Control plane ready — provisioning through the **{cp.surface}** surface "
        f"(admin prefix `{cp.prefix or '/'}`)."
        if cp
        else "> **Set `HIGHFLAME_REGISTRAR_TOKEN` or `HIGHFLAME_INTERNAL_SERVICE_SECRET` in `.env` to run this notebook.**"
    )
    return (cp,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ---
        ## 1. The Passport — a registration record and a short-lived credential

        ODIS splits identity in two: a **durable governance record** (who owns
        this agent, what it may ever do) and an **ephemeral runtime credential**
        (what this running instance is presenting right now).

        Registration is a one-time act by your platform team or provisioning
        pipeline — not something the agent does at every boot.
        """
    )
    return


@app.cell
def _(cfg, cp, mo, unique):
    orch_record, orch_key = (
        cp.provision(
            external_id=unique("research-orchestrator"),
            owner_user_id=cfg.owner_user_id,
            scopes=["tools:read", "tools:execute"],
            trust_level="first_party",
            framework="python-sdk",
            publisher="cookbook-demo",
        )
        if cp
        else (None, None)
    )

    mo.md(
        f"""
        **Registered.**

        | ODIS §6.1 field | Value |
        | --- | --- |
        | `agent_id` | `{orch_record['external_id']}` |
        | identifier (WIMSE/SPIFFE) | `{orch_record['wimse_uri']}` |
        | `sponsor_ref` / `owner_ref` | `{orch_record['owner_user_id']}` |
        | `lifecycle_state` | `{orch_record['status']}` |
        | `trust_domain` | `{orch_record['wimse_uri'].split('/')[2]}` |
        | `policy_profile_ref` | `{orch_record.get('credential_policy_id')}` |

        The identifier is a SPIFFE/WIMSE URI that embeds trust domain, tenant,
        project and agent — the principal is self-describing. Registration
        **without an owner is rejected** (ODIS-CC-05); that is what stops the
        inventory rotting into unattributable service accounts.
        """
        if orch_record
        else "_skipped — no provisioning credential_"
    )
    return orch_key, orch_record


@app.cell
def _(Agent, cfg, mo, orch_key, orch_record, verify_local):
    orchestrator = (
        Agent(
            authn_url=cfg.authn_url,
            bootstrap_key=orch_key,
            wimse_uri=orch_record["wimse_uri"],
            identity_id=orch_record["id"],
        )
        if orch_record
        else None
    )
    orch_cred = orchestrator.token() if orchestrator else None
    orch_claims = verify_local(cfg.authn_url, orch_cred["access_token"]) if orch_cred else {}

    mo.md(
        f"""
        **The runtime credential.** The agent boots holding a bootstrap key from
        your secret store, and exchanges it for this:

        | Claim | Value |
        | --- | --- |
        | `sub` | `{orch_claims.get('sub')}` |
        | lifetime | **{int(orch_claims.get('exp', 0)) - int(orch_claims.get('iat', 0))}s** — finite and bounded (ODIS-L1-05) |
        | `jti` | `{orch_claims.get('jti')}` |
        | granted scopes | `{orch_claims.get('scopes')}` |
        | `trust_level` | `{orch_claims.get('trust_level')}` |
        | `status` | `{orch_claims.get('status')}` |

        Verified offline against the issuer's JWKS — no round-trip. The
        credential carries the registration's governance state, so anyone
        validating it learns whether the identity is still active.
        """
        if orch_cred
        else "_skipped_"
    )
    return orch_claims, orch_cred, orchestrator


@app.cell
def _(mo):
    mo.md(
        r"""
        ---
        ## 2. The Bridge — delegation that can only narrow

        This is the layer most agent stacks don't have, and the one that decides
        whether multi-agent systems stay containable.

        The sub-agent registers a **public key** and proves it holds the private
        half. A stolen credential alone is not enough (ODIS-L1-09).
        """
    )
    return


@app.cell
def _(Agent, cfg, cp, mo, new_holder_keypair, unique):
    sub_scopes = ["tools:read"]  # deliberately narrower than the orchestrator
    sub_private, sub_public = new_holder_keypair() if cp else (None, "")
    sub_record, sub_key = (
        cp.provision(
            external_id=unique("summariser"),
            owner_user_id=cfg.owner_user_id,
            scopes=sub_scopes,
            trust_level="first_party",
            public_key_pem=sub_public,
        )
        if cp
        else (None, None)
    )
    sub_agent = (
        Agent(
            authn_url=cfg.authn_url,
            bootstrap_key=sub_key,
            wimse_uri=sub_record["wimse_uri"],
            identity_id=sub_record["id"],
            holder_private_key=sub_private,
        )
        if sub_record
        else None
    )

    mo.md(
        f"""
        | | Orchestrator | Sub-agent |
        | --- | --- | --- |
        | registered authority | `tools:read`, `tools:execute` | `tools:read` |
        | holder key | — | ✅ registered |

        The sub-agent is registered for **strictly less** than its parent.
        """
        if sub_record
        else "_skipped_"
    )
    return sub_agent, sub_key, sub_private, sub_public, sub_record, sub_scopes


@app.cell
def _(cfg, delegate, mo, orch_claims, orch_cred, sub_agent, verify_local):
    delegated = (
        delegate(
            cfg.authn_url,
            subject_token=orch_cred["access_token"],
            actor_assertion=sub_agent.holder_assertion(audience=orch_claims["iss"]),
            scope="tools:read",
        )
        if sub_agent
        else None
    )
    del_claims = verify_local(cfg.authn_url, delegated["access_token"]) if delegated else {}

    mo.md(
        f"""
        **Delegated credential** (RFC 8693 token exchange) — ODIS §6.3:

        | Field | Value |
        | --- | --- |
        | `sub` (who acts) | `{del_claims.get('sub')}` |
        | `act.sub` (on whose behalf) | `{(del_claims.get('act') or {}).get('sub')}` |
        | `delegation_depth` | `{del_claims.get('delegation_depth')}` |
        | granted scopes | `{del_claims.get('scopes')}` |
        | `task_id` (mission) | `{del_claims.get('mission_id')}` |

        The chain is authenticated and auditable: every action this sub-agent
        takes is attributable to both itself *and* the human behind its parent.
        """
        if delegated
        else "_skipped_"
    )
    return del_claims, delegated


@app.cell
def _(ODISRecipeError, cfg, delegate, mo, orch_claims, orch_cred, sub_agent, verify_local):
    # The orchestrator genuinely holds tools:execute. Try to pass it down.
    try:
        _escalated = delegate(
            cfg.authn_url,
            subject_token=orch_cred["access_token"],
            actor_assertion=sub_agent.holder_assertion(audience=orch_claims["iss"]),
            scope="tools:read tools:execute",
        )
        _granted = verify_local(cfg.authn_url, _escalated["access_token"]).get("scopes")
        _outcome = f"granted `{_granted}` — `tools:execute` was **dropped**"
    except ODISRecipeError as _exc:
        _outcome = f"refused — `{str(_exc)[:90]}`"

    try:
        delegate(
            cfg.authn_url,
            subject_token=orch_cred["access_token"],
            actor_assertion=sub_agent.holder_assertion(audience=orch_claims["iss"]),
            scope="tools:execute",
        )
        _only = "**ACCEPTED — investigate**"
    except ODISRecipeError as _exc2:
        _only = f"refused — `{str(_exc2)[:80]}`"

    mo.md(
        f"""
        ### Escalation attempt

        | Requested | Result |
        | --- | --- |
        | `tools:read tools:execute` | {_outcome} |
        | `tools:execute` only | {_only} |

        Granted scope is the intersection of *requested* ∩ *what the parent
        holds* ∩ *what the sub-agent is registered for* (ODIS-L2-01, L2-06).

        > The orchestrator **has** `tools:execute` and still cannot pass it on.
        > The ceiling lives in the sub-agent's registration, not in the calling
        > code — so it holds even when the calling code is the thing that has
        > gone wrong. A prompt-injected orchestrator cannot escalate its children.
        """
        if sub_agent
        else "_skipped_"
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ---
        ## 3. The Router — the governance checkpoint

        Every action is evaluated *before* it happens, against the identity
        that is asking — not just the text it contains.
        """
    )
    return


@app.cell
def _(cfg, delegated, guard, mo, orch_cred):
    _rows = []
    if delegated:
        for _who, _tok, _action, _content in [
            ("orchestrator", orch_cred["access_token"], "process_prompt", "Summarise the Q3 report"),
            ("orchestrator", orch_cred["access_token"], "call_tool", "run the deploy script"),
            ("sub-agent (delegated)", delegated["access_token"], "process_prompt", "Summarise the Q3 report"),
            ("sub-agent (delegated)", delegated["access_token"], "call_tool", "run the deploy script"),
        ]:
            _o = guard(cfg.shield_url, _tok, content=_content, action=_action)
            if _o.no_policies:
                _verdict = "⚠️ fail-closed — no policies enabled in this tenant"
            else:
                _icon = {"allow": "✅", "modify": "✏️", "deny": "⛔"}.get(_o.decision, "❔")
                _verdict = f"{_icon} `{_o.decision}`"
            _rows.append(
                f"| {_who} | `{_action}` | {_verdict} | {_o.reason or ''} | "
                f"{', '.join(s[0] for s in _o.signals) or '—'} |"
            )

    mo.md(
        "| Principal | Action | Decision | Reason | Signals |\n"
        "| --- | --- | --- | --- | --- |\n" + "\n".join(_rows)
        + """

> The delegated sub-agent is denied `call_tool` with
> **`insufficient_scope`** — Layer 2's attenuation, enforced at Layer 3.
> This check runs *before* Cedar policy evaluation, so a missing scope is a
> **hard ceiling**, not a policy opinion a misconfigured rule could waive.
"""
        if _rows
        else "_skipped_"
    )
    return


@app.cell
def _(cfg, guard, mo, orch_cred):
    _ident = None
    if orch_cred:
        _ident = guard(
            cfg.shield_url, orch_cred["access_token"],
            content="ping", action="process_prompt",
        ).identity

    mo.md(
        f"""
        ### The identity-context object (ODIS-L3-06)

        This is what the checkpoint decided on, returned to you:

        ```json
        {_ident}
        ```

        Policies can key on trust level, delegation depth, ownership or
        credential age — not only on content. That is the practical difference
        between a guardrail bolted onto a prompt and a governance checkpoint.
        """
        if _ident
        else "_skipped_"
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ---
        ## 4. Revocation and the kill switch

        ODIS allows 300 seconds for revocation to propagate inside a trust
        domain. Measured at the enforcement point:
        """
    )
    return


@app.cell
def _(cfg, cp, del_claims, delegated, guard, mo, sub_agent):
    _before = _after = None
    if delegated:
        _before = guard(cfg.shield_url, delegated["access_token"],
                        content="ping", action="process_prompt").status != 401
        cp.revoke_credential(identity_id=sub_agent.identity_id,
                             jti=del_claims["jti"], reason="task complete")
        _after = guard(cfg.shield_url, delegated["access_token"],
                       content="ping", action="process_prompt").status

    mo.md(
        f"""
        | Step | Result |
        | --- | --- |
        | checkpoint accepted the delegated credential | `{_before}` |
        | revoke one credential (a governance action) | done |
        | checkpoint now returns | **HTTP {_after}** {"— rejected" if _after == 401 else ""} |

        > **Offline JWKS verification is *not* revocation-aware.** This
        > credential still passes a local signature check until it expires.
        > That is the correct trade — no network call on a hot path — but it
        > means local verification is not an authorization decision. Route
        > security-critical checks through the checkpoint.
        """
        if delegated
        else "_skipped_"
    )
    return


@app.cell
def _(cp, mo):
    _retired, _failed = cp.retire_all_created() if cp else (0, 0)
    mo.md(
        f"""
        ---
        ## 5. Retire

        The lifecycle stage most rollouts forget. Deactivating an identity
        revokes its credentials *and* stops its bootstrap key minting new ones —
        without that second half, offboarding is cosmetic. The record survives
        for audit.

        **{_retired} demo identities retired.**

        ---

        ### Where to go next

        - `python odis_conformance.py` — the full requirement-by-requirement table
        - `python secure_agent.py` — the same pattern as a plain script to copy
        - [`README.md`](README.md) — why each step is where it is, and the scope limits
        """
    )
    return


if __name__ == "__main__":
    app.run()
