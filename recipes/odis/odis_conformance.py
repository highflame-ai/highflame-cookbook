#!/usr/bin/env python3
"""ODIS conformance harness — prove each requirement against a live deployment.

Runs the three ODIS layers end to end and prints one row per requirement with
the evidence that satisfied it. Every row is produced by a real call: nothing
here is asserted from documentation.

    python odis_conformance.py            # human-readable table
    python odis_conformance.py --json     # machine-readable, for CI/evidence

Exit codes: 0 = every check passed or was legitimately skipped, 1 = a check
failed, 2 = the recipe could not run (missing configuration).

Spec: https://github.com/cosai-oasis/ws4-odis/blob/main/RFCs/ODIS.md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from odis_client import (
    ACTION_REQUIRED_SCOPE,
    Agent,
    Config,
    ODISRecipeError,
    delegate,
    guard,
    introspect,
    load_config,
    new_holder_keypair,
    unique,
    verify_local,
)

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"

# Two orthogonal axes, deliberately kept apart.
#
#   status  — did the behaviour this run exercised do what we expected?
#             PASS/FAIL/SKIP. This is the regression signal CI cares about.
#   verdict — how much of the ODIS requirement does the platform actually
#             satisfy? Meets/Partial/Gap. This is the honesty signal.
#
# They are not the same thing, and collapsing them is how a conformance
# artifact starts over-claiming: a green run against the slice of a
# requirement you chose to test says nothing about the parts you skipped.
# A check can PASS and still be a Partial — most of the interesting ones are.
#
# Verdict vocabulary follows the ZeroID ODIS role-capability statement, so the
# two documents can be read side by side.
MEETS, PARTIAL, GAP, NA = "Meets", "Partial", "Gap", "N/A"


@dataclass
class Check:
    req: str
    layer: str
    title: str
    status: str = SKIP
    evidence: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    verdict: str = MEETS
    limitation: str = ""


class Harness:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.checks: list[Check] = []
        self.cp = cfg.control_plane()

    def record(
        self,
        req: str,
        layer: str,
        title: str,
        status: str,
        evidence: str,
        *,
        verdict: str = MEETS,
        limitation: str = "",
        **detail: Any,
    ) -> None:
        self.checks.append(
            Check(req, layer, title, status, evidence, detail, verdict, limitation)
        )

    # -- helpers ----------------------------------------------------------

    def _agent(
        self, prefix: str, scopes: list[str], *, with_holder_key: bool = False, **kw: Any
    ) -> Agent:
        priv, pem = (None, "")
        if with_holder_key:
            priv, pem = new_holder_keypair()
        record, key = self.cp.provision(
            external_id=unique(prefix),
            owner_user_id=self.cfg.owner_user_id,
            scopes=scopes,
            public_key_pem=pem,
            **kw,
        )
        return Agent(
            authn_url=self.cfg.authn_url,
            bootstrap_key=key,
            wimse_uri=record["wimse_uri"],
            identity_id=record["id"],
            holder_private_key=priv,
        )

    def _checkpoint_accepts(self, token: str) -> bool:
        """True when the checkpoint authenticates the credential.

        Any non-401 answer means authentication succeeded — the credential got
        far enough to be decided on. A 401 means it was rejected at the door.
        """
        return guard(
            self.cfg.shield_url, token, content="ping", action="process_prompt"
        ).status != 401

    def _await_rejection(self, token: str, *, timeout_s: int = 310) -> float | None:
        """Poll the checkpoint until it rejects *token*. Returns seconds elapsed.

        ODIS-L3-04 allows up to 300s for revocation to propagate inside a trust
        domain, so this waits that long before calling it a failure.
        """
        start = time.monotonic()
        while (elapsed := time.monotonic() - start) < timeout_s:
            if not self._checkpoint_accepts(token):
                return elapsed
            time.sleep(2)
        return None

    def _introspect_note(self, token: str) -> str:
        """Best-effort issuer introspection — some deployments gate this endpoint."""
        try:
            return f"active={introspect(self.cfg.authn_url, token).get('active')}"
        except ODISRecipeError as exc:
            return f"unavailable ({str(exc)[:60]})"

    # =====================================================================
    # Layer 1 — the Passport
    # =====================================================================

    def layer1(self) -> None:
        record, key = self.cp.provision(
            external_id=unique("odis-l1"),
            owner_user_id=self.cfg.owner_user_id,
            scopes=["tools:read"],
            trust_level="first_party",
            framework="python-sdk",
            publisher="highflame-cookbook",
            capabilities=["summarise"],
        )

        # ODIS-CC-05 — a registration record names an accountable human.
        self.record(
            "ODIS-CC-05", "L1",
            "Registration is authorized and names an accountable owner",
            PASS if record.get("owner_user_id") else FAIL,
            f"owner_user_id={record.get('owner_user_id')!r}",
            lifecycle_state=record.get("status"),
            trust_domain=record["wimse_uri"].split("/")[2],
        )

        # §6.1 — the Agent Registration Record's required fields.
        want = {
            "record_id": record.get("id"),
            "agent_id": record.get("external_id"),
            "lifecycle_state": record.get("status"),
            "sponsor_ref/owner_ref": record.get("owner_user_id"),
            "trust_domain": record["wimse_uri"].split("/")[2],
            "policy_profile_ref": record.get("credential_policy_id"),
        }
        missing = [k for k, v in want.items() if not v]
        self.record(
            "ODIS §6.1", "L1",
            "Agent Registration Record carries the required governance fields",
            PASS if not missing else FAIL,
            "all present" if not missing else f"missing: {missing}",
            **{k: str(v) for k, v in want.items()},
        )

        agent = Agent(
            authn_url=self.cfg.authn_url,
            bootstrap_key=key,
            wimse_uri=record["wimse_uri"],
            identity_id=record["id"],
        )
        tok = agent.token()
        claims = verify_local(self.cfg.authn_url, tok["access_token"])

        # ODIS-L1-01 — ephemeral, cryptographically verifiable credential.
        self.record(
            "ODIS-L1-01", "L1",
            "Agent authenticates with an ephemeral, verifiable credential",
            PASS if claims.get("sub") == record["wimse_uri"] else FAIL,
            f"JWKS-verified; sub={claims.get('sub')}",
            verdict=PARTIAL,
            limitation=(
                "the credential is ephemeral and verifiable, but this run obtained it "
                "with the api_key grant — a long-lived shared secret. ODIS-L1-01 is "
                "secret-zero elimination; a static bootstrap key does not achieve it. "
                "Private-key paths (RFC 7523 jwt-bearer, DPoP) exist and a credential "
                "policy can exclude api_key per identity, but that is not the default."
            ),
            jti=claims.get("jti"),
            issuer=claims.get("iss"),
        )

        # ODIS-L1-05 — finite, bounded lifetime.
        ttl = int(claims["exp"]) - int(claims["iat"])
        self.record(
            "ODIS-L1-05", "L1",
            "Credential lifetime is finite and bounded",
            PASS if 0 < ttl <= 86400 else FAIL,
            f"ttl={ttl}s (expires_in={tok.get('expires_in')})",
            verdict=PARTIAL,
            limitation=(
                "lifetimes are finite and policy-bounded, but rotation is "
                "client-initiated refresh. ODIS's 'MUST rotate automatically before "
                "expiry' is the SDK's obligation in this architecture, not the "
                "issuer's."
            ),
            exp=claims.get("exp"),
        )

        # §6.2 — the runtime credential descriptor binds back to the record.
        self.record(
            "ODIS §6.2", "L1",
            "Runtime credential binds to the active registration record",
            PASS
            if claims.get("status") == "active"
            and claims.get("account_id") == record["account_id"]
            else FAIL,
            f"status={claims.get('status')!r} identity_type={claims.get('identity_type')!r} "
            f"trust_level={claims.get('trust_level')!r}",
            owner_user_id=claims.get("owner_user_id"),
            scopes=claims.get("scopes"),
        )

        # ODIS-L1-09 — holder-bound proof-of-possession.
        holder = self._agent("odis-l1-pop", ["tools:read"], with_holder_key=True)
        assertion = holder.holder_assertion(audience=claims["iss"])
        self.record(
            "ODIS-L1-09", "L1",
            "Credentials can be holder-bound (proof-of-possession)",
            PASS if assertion else FAIL,
            "sub-agent self-signs ES256 with a registered public key; "
            "the private half never leaves the process",
            verdict=PARTIAL,
            limitation=(
                "holder binding is demonstrated on the delegation actor assertion. "
                "It is not global: DPoP is per-request opt-in with a Bearer fallback, "
                "and the api_key bootstrap path is a shared secret. The credential "
                "used everywhere else in this run is a bearer token."
            ),
            holder=holder.wimse_uri,
        )
        self._holder = holder
        self._issuer = claims["iss"]

    # =====================================================================
    # Layer 2 — the Bridge
    # =====================================================================

    def layer2(self) -> None:
        orchestrator = self._agent(
            "odis-l2-orch",
            ["tools:read", "tools:execute", "tools:write"],
            trust_level="first_party",
        )
        priv, pem = new_holder_keypair()
        sub_scopes = ["tools:read", "tools:execute"]  # deliberately NO tools:write
        sub_record, sub_key = self.cp.provision(
            external_id=unique("odis-l2-sub"),
            owner_user_id=self.cfg.owner_user_id,
            scopes=sub_scopes,
            trust_level="first_party",
            public_key_pem=pem,
        )
        sub = Agent(
            authn_url=self.cfg.authn_url,
            bootstrap_key=sub_key,
            wimse_uri=sub_record["wimse_uri"],
            identity_id=sub_record["id"],
            holder_private_key=priv,
        )

        parent = orchestrator.token()
        delegated = delegate(
            self.cfg.authn_url,
            subject_token=parent["access_token"],
            actor_assertion=sub.holder_assertion(audience=self._issuer),
            scope="tools:read",
        )
        dc = verify_local(self.cfg.authn_url, delegated["access_token"])

        # §6.3 / ODIS-L2-05 — the delegation record and its lineage.
        act = dc.get("act") or {}
        self.record(
            "ODIS-L2-05", "L2",
            "Delegation record carries an authenticated chain",
            PASS
            if dc.get("sub") == sub.wimse_uri
            and act.get("sub") == orchestrator.wimse_uri
            else FAIL,
            f"sub={dc.get('sub')} act.sub={act.get('sub')} depth={dc.get('delegation_depth')}",
            verdict=PARTIAL,
            limitation=(
                "carried as JWT claims, which §6.3 permits — but an OAuth-native "
                "carrier only inherits 6 of the 13 MUST fields. Absent: "
                "originating_authorization_ref, resource_indicators, constraints, "
                "attenuation_profile_ref. Partial: parent_delegation_ref (no digest "
                "match), delegation_chain (single-level act, not the ordered hop "
                "list), task_id (mission_id is a correlation key, not declared "
                "purpose)."
            ),
            delegation_id=dc.get("jti"),
            task_id=dc.get("mission_id"),
        )

        # ODIS-L2-01 / L2-06 — authority narrows, never widens.
        widened = None
        widen_error = None
        try:
            widened = delegate(
                self.cfg.authn_url,
                subject_token=parent["access_token"],
                actor_assertion=sub.holder_assertion(audience=self._issuer),
                scope="tools:read tools:write",
            )
            wc = verify_local(self.cfg.authn_url, widened["access_token"])
            leaked = "tools:write" in (wc.get("scopes") or [])
        except ODISRecipeError as exc:
            widen_error = str(exc)
            leaked = False
            wc = {}

        self.record(
            "ODIS-L2-06", "L2",
            "Sub-agent authority is equal to or narrower than the parent's",
            FAIL if leaked else PASS,
            (
                f"requested 'tools:read tools:write'; granted {wc.get('scopes')} "
                "— the parent holds tools:write but the sub-agent is not "
                "registered for it, so it was dropped"
            )
            if not widen_error
            else f"exchange refused: {widen_error[:120]}",
            verdict=PARTIAL,
            limitation=(
                "narrowing is monotonic, but by set intersection over a controlled "
                "scope vocabulary — lexical, not the semantic attenuation_profile_ref "
                "mechanism ODIS-L2-06 specifies. Sufficient while the issuer owns the "
                "vocabulary; insufficient for cross-vendor scope semantics."
            ),
            orchestrator_scopes=parent.get("scope"),
            sub_agent_registered=sub_record.get("allowed_scopes") or sub_scopes,
        )

        # An escalation with nothing in the intersection must be refused outright.
        refused = None
        try:
            delegate(
                self.cfg.authn_url,
                subject_token=parent["access_token"],
                actor_assertion=sub.holder_assertion(audience=self._issuer),
                scope="tools:write",
            )
        except ODISRecipeError as exc:
            refused = str(exc)
        self.record(
            "ODIS-L2-01", "L2",
            "Effective authority is the intersection, and an empty one fails closed",
            PASS if refused and "invalid_scope" in refused else FAIL,
            f"requesting only 'tools:write' -> {('refused: ' + refused[:90]) if refused else 'ACCEPTED (unexpected)'}",
            verdict=PARTIAL,
            limitation=(
                "the fail-closed behaviour is complete, but ODIS-L2-01 enumerates the "
                "intersection's inputs as principal ∩ registration ∩ parent ∩ task ∩ "
                "resource ∩ environmental constraints. This intersects scopes, depth "
                "and TTL and resolves the registration; it models no task, resource or "
                "constraint dimension."
            ),
        )

        # ODIS-L2-14 — resolve to an active registration before granting authority.
        self.cp.deactivate(sub.identity_id)
        time.sleep(0.5)
        post_deactivation = None
        try:
            delegate(
                self.cfg.authn_url,
                subject_token=parent["access_token"],
                actor_assertion=sub.holder_assertion(audience=self._issuer),
                scope="tools:read",
            )
        except ODISRecipeError as exc:
            post_deactivation = str(exc)
        self.record(
            "ODIS-L2-14", "L2",
            "Delegation resolves the credential to an ACTIVE registration first",
            PASS if post_deactivation else FAIL,
            f"after deactivating the sub-agent: "
            f"{('refused: ' + post_deactivation[:90]) if post_deactivation else 'still issued (unexpected)'}",
        )

        # Child credential must not outlive its parent.
        child_exp, parent_exp = dc.get("exp"), verify_local(
            self.cfg.authn_url, parent["access_token"]
        ).get("exp")
        self.record(
            "ODIS §6.3", "L2",
            "Delegated credential never outlives its parent",
            PASS if child_exp and parent_exp and child_exp <= parent_exp else FAIL,
            f"child exp {child_exp} <= parent exp {parent_exp}",
        )

        self._delegated_token = delegated["access_token"]

    # =====================================================================
    # Layer 3 — the Router
    # =====================================================================

    def layer3(self) -> None:
        # A token that is missing the scope its action requires.
        under = self._agent("odis-l3-under", ["tools:execute"], trust_level="first_party")
        out = guard(
            self.cfg.shield_url,
            under.access_token(),
            content="Summarise the Q3 revenue report",
            action="process_prompt",
        )

        # ODIS-L3-06 — a structured identity-context object reaches the policy engine.
        self.record(
            "ODIS-L3-06", "L3",
            "Checkpoint emits a structured identity-context object",
            PASS if out.identity else FAIL,
            f"agent_identity={json.dumps(out.identity)}" if out.identity else "absent",
            limitation=(
                "note: the ZeroID role-capability statement marks L3-06 a Gap, "
                "correctly — an authorization server has no policy checkpoint. "
                "Highflame satisfies it in Shield, a separate component. Read the two "
                "documents together: the AS-scoped statement and this platform-scoped "
                "run disagree because they describe different scopes, not different "
                "facts."
            ),
            request_trace_id=out.request_id,
        )

        # The pre-policy scope ceiling — Layer 2 attenuation enforced at Layer 3.
        self.record(
            "ODIS-L3-02", "L3",
            "Requested action is evaluated against the credential's authority",
            PASS
            if out.denied and any(s[0] == "insufficient_scope" for s in out.signals)
            else FAIL,
            f"decision={out.decision!r} reason={out.reason!r} signals={out.signals}",
            required_scope=ACTION_REQUIRED_SCOPE["process_prompt"],
            token_scopes="tools:execute",
        )

        # ODIS "fail-closed mediation" (Core profile).
        ok = self._agent("odis-l3-ok", ["tools:read"], trust_level="first_party")
        allow_out = guard(
            self.cfg.shield_url,
            ok.access_token(),
            content="Summarise the Q3 revenue report",
            action="process_prompt",
        )
        if allow_out.no_policies:
            self.record(
                "ODIS Core", "L3",
                "Mediation fails closed when policy cannot be evaluated",
                PASS,
                "tenant has no Cedar policies loaded; the checkpoint refused to "
                "evaluate rather than defaulting to allow",
                http_status=allow_out.status,
            )
            self.record(
                "ODIS-L3-02b", "L3",
                "A correctly-scoped credential clears the ceiling",
                SKIP,
                "reached policy evaluation, but this tenant has no policies "
                "enabled — enable one in Studio to see an allow",
            )
        else:
            self.record(
                "ODIS Core", "L3",
                "Mediation fails closed when policy cannot be evaluated",
                SKIP,
                "tenant has policies loaded, so this negative path did not trigger",
            )
            self.record(
                "ODIS-L3-02b", "L3",
                "A correctly-scoped credential clears the ceiling",
                PASS if allow_out.decision else FAIL,
                f"decision={allow_out.decision!r} reason={allow_out.reason!r}",
                signals=str(allow_out.signals),
            )

        # ODIS-CC-01 / CC-06 — correlatable audit anchor.
        self.record(
            "ODIS-CC-01", "L3",
            "Every decision is logged with a correlation identifier",
            PASS if out.request_id else FAIL,
            f"request_id={out.request_id}",
            receipt="present (signed)" if out.receipt else "receipt signing disabled",
        )

        # ODIS-L3-04 — revocation, measured where it matters: at the checkpoint.
        # (Introspection at the issuer is the other signal, but some deployments
        # require client authentication on that endpoint, so it is best-effort.)
        tok = ok.token(force=True)
        before = self._checkpoint_accepts(tok["access_token"])
        self.cp.revoke_credential(
            identity_id=ok.identity_id,
            jti=tok["jti"],
            reason="ODIS-L3-04 conformance check",
        )
        propagation = self._await_rejection(tok["access_token"], timeout_s=310)
        still_verifies = True
        try:
            verify_local(self.cfg.authn_url, tok["access_token"])
        except Exception:
            still_verifies = False
        self.record(
            "ODIS-L3-04", "L3",
            "Revocation propagates to the enforcement point within 300s",
            PASS if before and propagation is not None else FAIL,
            (
                f"checkpoint accepted the credential, then rejected it "
                f"{propagation:.1f}s after revocation"
                if propagation is not None
                else "checkpoint still accepted the credential after revocation"
            ),
            verdict=PARTIAL,
            limitation=(
                "the mechanism works and is measured here, per run. ODIS-L3-04 asks "
                "for a *declared, published* maximum latency, and ODIS-CC-03 for a "
                "reproducible benchmark report. Neither exists — a number observed on "
                "one developer machine is evidence, not a service level."
            ),
            issuer_introspection=self._introspect_note(tok["access_token"]),
            caveat=(
                "offline JWKS verification still accepts this credential until it "
                "expires — use the checkpoint or introspection when the decision "
                "is security-critical"
                if still_verifies
                else "offline verification also rejects it"
            ),
        )

        # ODIS-L3-05 — single-operation global de-provisioning (kill switch).
        victim = self._agent("odis-l3-kill", ["tools:read"], trust_level="first_party")
        issued = victim.token(force=True)
        assert self._checkpoint_accepts(issued["access_token"])
        self.cp.deactivate(victim.identity_id)
        remint_failed = None
        try:
            victim.token(force=True)
        except ODISRecipeError as exc:
            remint_failed = str(exc)
        killed = self._await_rejection(issued["access_token"], timeout_s=310)
        self.record(
            "ODIS-L3-05", "L3",
            "Immediate global de-provisioning via a single operation",
            PASS if remint_failed and killed is not None else FAIL,
            f"one deactivation call -> the bootstrap key can no longer mint "
            f"({'refused' if remint_failed else 'STILL MINTS'}), and the "
            f"already-issued credential stopped being accepted "
            f"{f'{killed:.1f}s later' if killed is not None else 'NEVER (still accepted)'}",
        )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

LAYER_NAMES = {
    "L1": "Layer 1 — The Passport (identity & attestation)",
    "L2": "Layer 2 — The Bridge (delegation & access)",
    "L3": "Layer 3 — The Router (discovery & governance)",
}
GLYPH = {PASS: "PASS", FAIL: "FAIL", SKIP: "SKIP"}


def render(checks: list[Check], cfg: Config) -> None:
    print()
    print("=" * 78)
    print("  ODIS conformance — Highflame")
    print("=" * 78)
    print(f"  identity plane : {cfg.authn_url}")
    print(f"  checkpoint     : {cfg.shield_url}")
    print(f"  tenant         : {cfg.account_id}/{cfg.project_id}")
    print("=" * 78)

    for layer in ("L1", "L2", "L3"):
        rows = [c for c in checks if c.layer == layer]
        if not rows:
            continue
        print(f"\n{LAYER_NAMES[layer]}\n{'-' * 78}")
        for c in rows:
            mark = "" if c.verdict == MEETS else f"  [{c.verdict}]"
            print(f"  [{GLYPH[c.status]}] {c.req:<14} {c.title}{mark}")
            for line in _wrap(c.evidence, 68):
                print(f"         {line}")
            if c.limitation:
                for line in _wrap(f"limitation — {c.limitation}", 66):
                    print(f"           {line}")
            for k, v in c.detail.items():
                if v:
                    print(f"           - {k}: {v}")

    npass = sum(1 for c in checks if c.status == PASS)
    nfail = sum(1 for c in checks if c.status == FAIL)
    nskip = sum(1 for c in checks if c.status == SKIP)
    nmeets = sum(1 for c in checks if c.verdict == MEETS and c.status != SKIP)
    npartial = sum(1 for c in checks if c.verdict == PARTIAL)

    print("\n" + "=" * 78)
    print(f"  behaviour : {npass} passed, {nfail} failed, {nskip} skipped")
    print(f"  conformance: {nmeets} Meets, {npartial} Partial")
    print("=" * 78)
    print(
        "\n  A PASS means the behaviour exercised did what was expected. It is NOT a\n"
        "  conformance claim: several requirements are only partially satisfied, and\n"
        "  the limitation notes above say how. Requirements this run does not touch\n"
        "  at all (software/hardware attestation, bridge mode, presenter isolation,\n"
        "  velocity limits) are absent rather than passing — see README.md.\n"
    )


def _wrap(text: str, width: int) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width) or [""]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args()

    cfg = load_config()
    if not cfg.can_provision:
        print(
            "SKIP: this recipe provisions agent identities, which needs either\n"
            "  HIGHFLAME_REGISTRAR_TOKEN (a Bearer token with the nhi:manage scope), or\n"
            "  HIGHFLAME_INTERNAL_SERVICE_SECRET (self-hosted deployments).\n"
            "See .env.example.",
            file=sys.stderr,
        )
        return 2

    stages: list[tuple[str, Callable[[], None]]] = []
    try:
        h = Harness(cfg)
    except ODISRecipeError as exc:
        print(f"SKIP: {exc}", file=sys.stderr)
        return 2

    stages = [("Layer 1", h.layer1), ("Layer 2", h.layer2), ("Layer 3", h.layer3)]
    try:
        for name, fn in stages:
            try:
                fn()
            except ODISRecipeError as exc:
                h.record(name, name.replace("Layer ", "L"), f"{name} harness", FAIL, str(exc))
                break
            except Exception as exc:  # noqa: BLE001 - report, don't crash the harness
                h.record(
                    name,
                    name.replace("Layer ", "L"),
                    f"{name} harness",
                    FAIL,
                    f"{type(exc).__name__}: {exc}",
                )
                break
    finally:
        # Retire what this run provisioned, even if a stage blew up. Leaving
        # live agent identities behind would be an odd way to end a recipe
        # about identity governance.
        retired, failed = h.cp.retire_all_created()

    if args.json:
        print(json.dumps(
            {
                "target": {
                    "authn_url": cfg.authn_url,
                    "shield_url": cfg.shield_url,
                    "account_id": cfg.account_id,
                    "project_id": cfg.project_id,
                },
                "checks": [asdict(c) for c in h.checks],
            },
            indent=2,
        ))
    else:
        render(h.checks, cfg)
        print(
            f"  retired {retired} demo identities"
            + (f" ({failed} failed)" if failed else "")
            + "\n"
        )

    return 1 if any(c.status == FAIL for c in h.checks) else 0


if __name__ == "__main__":
    sys.exit(main())
