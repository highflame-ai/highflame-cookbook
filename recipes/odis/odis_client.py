"""Shared helpers for the ODIS recipe.

One module, three concerns:

* :class:`ControlPlane` — the ODIS **Layer 1 registration** surface. Creates
  agent identities and bootstrap keys. Works against either deployment shape
  (see "Two deployment shapes" below).
* :class:`Agent` — an ODIS **Layer 1 runtime credential** holder. Exchanges a
  bootstrap key for a short-lived, verifiable credential, and can self-sign the
  holder-of-key assertion that ODIS Layer 2 delegation requires.
* :func:`guard` — the ODIS **Layer 3 governance checkpoint** call.

Two deployment shapes
---------------------
Highflame's identity layer is ZeroID. It ships in two shapes, and they mount
their admin API at different prefixes:

===========================  ==================  =========================
Shape                        Admin prefix        Token endpoint
===========================  ==================  =========================
ZeroID embedded in AuthN     ``/`` (host root)   ``/oauth2/token``
ZeroID standalone            ``/api/v1``         ``/oauth2/token``
===========================  ==================  =========================

``ControlPlane`` probes for the prefix at construction, so the recipe runs
unchanged against either. The SDK's ``highflame.zeroid.ZeroIDClient`` targets one
shape at a time (0.3.23 uses host-root paths, so it drives AuthN and 404s against
a standalone ZeroID); this helper is deliberately deployment-agnostic, and being
raw HTTP it also shows the wire format a conformance exercise is about.

If you are writing an application rather than reading a spec walkthrough, prefer
the SDK — 0.3.23 ships ``generate_keypair()`` and ``build_actor_assertion()``,
which replace the holder-of-key mechanics spelled out by hand below.

Nothing here is Highflame-internal — every call is a documented HTTP endpoint.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_AUTHN = "http://localhost:8051"
DEFAULT_SHIELD = "http://localhost:8070"

# Re-exchange this many seconds before a credential actually expires, so an
# in-flight request never carries one that dies mid-call.
_REFRESH_BUFFER_S = 60

# The privilege-scope vocabulary Shield enforces as a pre-Cedar hard ceiling.
# Source of truth: highflame-policy/schemas/privilege_catalog.json.
SCOPES = {
    "tools:read": "Read workspace files; feed prompts/context to the model.",
    "tools:write": "Create, modify, or delete files.",
    "tools:execute": "Invoke MCP tools, native IDE tools, and shell commands.",
    "tools:network": "Outbound HTTP; connect to remote MCP servers.",
    "tools:agent": "Spawn or delegate to sub-agents.",
    "tools:vcs": "Commit, branch, push, open pull requests.",
}

# Action -> required scope. Shield rejects with `insufficient_scope` BEFORE any
# Cedar policy runs, so a missing scope is a hard ceiling, not a policy opinion.
ACTION_REQUIRED_SCOPE = {
    "process_prompt": "tools:read",
    "read_file": "tools:read",
    "call_tool": "tools:execute",
    "write_file": "tools:write",
    "connect_server": None,  # deliberately no ceiling
}


class ODISRecipeError(RuntimeError):
    """Raised when the recipe cannot run for a configuration reason."""


# ---------------------------------------------------------------------------
# Layer 1 — registration (the durable governance record)
# ---------------------------------------------------------------------------


class ControlPlane:
    """The identity control plane: creates registration records and keys.

    Authentication, in order of preference:

    * ``registrar_token`` — a Bearer JWT carrying the ``nhi:manage`` scope,
      issued to a tenant "registrar" identity. **This is the production path**:
      no shared secret leaves the platform, and the tenant is derived from the
      token's own claims.
    * ``internal_secret`` + ``internal_service`` — the server-to-server path,
      available to first-party services in a self-hosted deployment. Convenient
      for local walkthroughs; not something an application should hold.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_AUTHN,
        *,
        account_id: str,
        project_id: str,
        registrar_token: str | None = None,
        internal_secret: str | None = None,
        internal_service: str = "highflame-admin",
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.account_id = account_id
        self.project_id = project_id
        self.timeout = timeout

        # Which surface we provision through depends on the credential, and the
        # two are NOT interchangeable:
        #
        #   registrar token -> /agents/*      (the NHI registry-management API)
        #   internal secret -> /identities, /api-keys
        #
        # A registrar token is deliberately confined to the registry surface —
        # the raw identity store answers 403 for it. So this is a real branch,
        # not a header swap.
        if registrar_token:
            self._auth = {"Authorization": f"Bearer {registrar_token}"}
            self.surface = "registry"
        elif internal_secret:
            self._auth = {
                "X-Internal-Service-Secret": internal_secret,
                "X-Internal-Service": internal_service,
            }
            self.surface = "identity-store"
        else:
            raise ODISRecipeError(
                "ControlPlane needs either registrar_token (a Bearer token with "
                "the nhi:manage scope) or internal_secret."
            )

        self.prefix = self._detect_prefix()

        # Every identity this control plane creates, so a demo run can retire
        # what it provisioned. A recipe about identity governance has no
        # business leaving orphaned agents behind — and nightly CI would
        # otherwise accumulate thousands of them.
        self.created_identities: list[str] = []

    # -- plumbing ---------------------------------------------------------

    @property
    def _headers(self) -> dict[str, str]:
        return {
            **self._auth,
            "X-Account-ID": self.account_id,
            "X-Project-ID": self.project_id,
            "Content-Type": "application/json",
        }

    def _detect_prefix(self) -> str:
        """Find whether admin routes live at the host root or under /api/v1."""
        probe = "/agents/registry" if self.surface == "registry" else "/identities"
        for prefix in ("", "/api/v1"):
            try:
                r = httpx.get(
                    f"{self.base_url}{prefix}{probe}",
                    headers=self._headers,
                    timeout=self.timeout,
                )
            except httpx.HTTPError as exc:  # pragma: no cover - network shape
                raise ODISRecipeError(
                    f"cannot reach the identity plane at {self.base_url}: {exc}"
                ) from exc
            if r.status_code in (401, 403):
                raise ODISRecipeError(
                    f"identity plane rejected the credential at {prefix or ''}{probe} "
                    f"({r.status_code}). A registrar token needs the nhi:manage scope; "
                    f"the internal secret needs a service name on the trusted list."
                )
            if r.status_code < 400:
                return prefix
        raise ODISRecipeError(
            f"no {probe} route found at {self.base_url} under '' or '/api/v1'"
        )

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = httpx.post(
            f"{self.base_url}{self.prefix}{path}",
            headers=self._headers,
            json=body,
            timeout=self.timeout,
        )
        if r.status_code >= 400:
            raise ODISRecipeError(f"POST {path} -> {r.status_code}: {r.text[:300]}")
        return r.json()

    def _patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = httpx.patch(
            f"{self.base_url}{self.prefix}{path}",
            headers=self._headers,
            json=body,
            timeout=self.timeout,
        )
        if r.status_code >= 400:
            raise ODISRecipeError(f"PATCH {path} -> {r.status_code}: {r.text[:300]}")
        return r.json()

    # -- ODIS Layer 1 -----------------------------------------------------

    def register(
        self,
        *,
        external_id: str,
        owner_user_id: str,
        allowed_scopes: list[str],
        name: str | None = None,
        trust_level: str = "unverified",
        identity_type: str = "agent",
        public_key_pem: str = "",
        framework: str = "",
        publisher: str = "",
        capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create an ODIS **Agent Registration Record**.

        ``owner_user_id`` is mandatory (both here and server-side): every
        non-human identity must name an accountable human. That is ODIS-CC-05.
        """
        if self.surface == "registry":
            # /agents/register creates the identity AND its bootstrap key
            # atomically. Note the field name: there is no `owner_user_id` here
            # — the server derives the owner from `created_by`. Omit it and
            # registration fails with "owner_user_id is required", naming a
            # field this endpoint does not accept.
            body = self._post(
                "/agents/register",
                {
                    "name": name or external_id,
                    "external_id": external_id,
                    "identity_type": identity_type,
                    "trust_level": trust_level,
                    "allowed_scopes": allowed_scopes,
                    "public_key_pem": public_key_pem,
                    "framework": framework,
                    "publisher": publisher,
                    "capabilities": capabilities or [],
                    "created_by": owner_user_id,
                },
            )
            record = dict(body["identity"])
            record["_api_key"] = body["api_key"]
        else:
            record = self._post(
                "/identities",
                {
                    "external_id": external_id,
                    "owner_user_id": owner_user_id,
                    "name": name or external_id,
                    "identity_type": identity_type,
                    "trust_level": trust_level,
                    "allowed_scopes": allowed_scopes,
                    "public_key_pem": public_key_pem,
                    "framework": framework,
                    "publisher": publisher,
                    "capabilities": capabilities or [],
                },
            )
        self.created_identities.append(record["id"])
        return record

    def issue_key(
        self, *, identity_id: str, name: str, scopes: list[str]
    ) -> str:
        """Mint the bootstrap key an agent uses to obtain runtime credentials.

        Returned plaintext is shown **once**. In production this is written
        straight into the workload's secret store, never logged.
        """
        return self._post(
            "/api-keys",
            {"name": name, "identity_id": identity_id, "scopes": scopes},
        )["key"]

    def credentials(self, identity_id: str) -> list[dict[str, Any]]:
        """List issued credentials for an identity (the audit trail per agent)."""
        r = httpx.get(
            f"{self.base_url}{self.prefix}/credentials",
            headers=self._headers,
            params={"identity_id": identity_id},
            timeout=self.timeout,
        )
        if r.status_code >= 400:
            raise ODISRecipeError(f"GET /credentials -> {r.status_code}: {r.text[:200]}")
        return r.json().get("credentials") or []

    def revoke_credential(
        self, *, identity_id: str, jti: str, reason: str = "cookbook demo"
    ) -> dict[str, Any]:
        """Revoke a single issued credential, identified by its ``jti``.

        Revocation is a **governance** action, not something the credential
        holder performs — so it lives on the administrative surface rather than
        on the RFC 7009 endpoint (which many deployments gate behind client
        authentication).

        Note the indirection: a credential *record* has its own ``id``, distinct
        from the ``jti`` carried in the token. Callers hold the ``jti``, so this
        resolves it to the record first.
        """
        for cred in self.credentials(identity_id):
            if cred.get("jti") == jti:
                return self._post(f"/credentials/{cred['id']}/revoke", {"reason": reason})
        raise ODISRecipeError(f"no credential record found for jti {jti}")

    def deactivate(self, identity_id: str) -> dict[str, Any]:
        """ODIS-L3-05 kill switch: de-provision an identity in one operation."""
        if self.surface == "registry":
            return self._post(f"/agents/registry/{identity_id}/deactivate", {})
        return self._patch(f"/identities/{identity_id}", {"status": "deactivated"})

    def retire_all_created(self) -> tuple[int, int]:
        """Retire every identity this control plane created. Returns (retired, failed).

        This is the *Retire* stage of the identity lifecycle: a soft retire that
        deactivates the identity and revokes its credentials while preserving
        the record for audit. Best-effort and idempotent — an already-retired
        identity is a no-op.
        """
        retired = failed = 0
        for identity_id in self.created_identities:
            try:
                self.deactivate(identity_id)
                retired += 1
            except ODISRecipeError:
                failed += 1
        return retired, failed

    def provision(
        self,
        *,
        external_id: str,
        owner_user_id: str,
        scopes: list[str],
        trust_level: str = "unverified",
        public_key_pem: str = "",
        **kwargs: Any,
    ) -> tuple[dict[str, Any], str]:
        """Register + issue a key in one step. Returns ``(record, bootstrap_key)``."""
        record = self.register(
            external_id=external_id,
            owner_user_id=owner_user_id,
            allowed_scopes=scopes,
            trust_level=trust_level,
            public_key_pem=public_key_pem,
            **kwargs,
        )
        # The registry surface already minted a bootstrap key as part of
        # registration; the identity-store surface needs a second call.
        key = record.pop("_api_key", None)
        if key is None:
            key = self.issue_key(
                identity_id=record["id"], name=f"{external_id}-key", scopes=scopes
            )
        return record, key


# ---------------------------------------------------------------------------
# Layer 1 — the runtime credential
# ---------------------------------------------------------------------------


def new_holder_keypair() -> tuple[Any, str]:
    """Generate an EC P-256 keypair for holder-of-key proof (ODIS-L1-09).

    The private half never leaves the process. Only the PEM-encoded public half
    is registered, so the platform can verify a signature it can never forge.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_key, public_pem


@dataclass
class Agent:
    """An agent holding an ODIS runtime credential.

    ``bootstrap_key`` is the long-lived secret; ``token()`` exchanges it for a
    short-lived credential. Nothing downstream ever sees the bootstrap key.
    """

    authn_url: str
    bootstrap_key: str
    wimse_uri: str = ""
    identity_id: str = ""
    holder_private_key: Any = None
    _cached: dict[str, Any] | None = field(default=None, repr=False)
    _cached_until: float = field(default=0.0, repr=False)

    # -- runtime credential ----------------------------------------------

    def token(self, *, scope: str = "", force: bool = False) -> dict[str, Any]:
        """Exchange the bootstrap key for a short-lived credential.

        This is ODIS-L1-01 (ephemeral, cryptographically verifiable) and
        ODIS-L1-05 (finite, bounded lifetime) in one call.

        The result is cached until shortly before it expires, then re-exchanged.
        Caching without an expiry check is the classic bug here: the agent keeps
        presenting a dead credential and every call starts failing at once.
        """
        if self._cached and not force and not scope and not self._expiring_soon():
            return self._cached
        body = {"grant_type": "api_key", "api_key": self.bootstrap_key}
        if scope:
            body["scope"] = scope
        r = httpx.post(f"{self.authn_url.rstrip('/')}/oauth2/token", json=body, timeout=20)
        if r.status_code >= 400:
            raise ODISRecipeError(f"token exchange failed {r.status_code}: {r.text[:300]}")
        tok = r.json()
        if not scope:
            self._cached = tok
            self._cached_until = time.time() + max(
                0, int(tok.get("expires_in") or 0) - _REFRESH_BUFFER_S
            )
        return tok

    def _expiring_soon(self) -> bool:
        return time.time() >= getattr(self, "_cached_until", 0.0)

    def access_token(self, *, scope: str = "") -> str:
        return self.token(scope=scope)["access_token"]

    # -- holder-of-key assertion (what Layer 2 delegation consumes) -------

    def holder_assertion(self, *, audience: str, ttl_seconds: int = 300) -> str:
        """Self-sign the proof-of-possession assertion for ODIS Layer 2.

        A delegated credential is only issued to a sub-agent that can prove it
        holds the private key matching its registered public key. The assertion
        is ES256, ``iss == sub == the agent's WIMSE URI``, ``aud == the issuer``.
        """
        import jwt as pyjwt

        if self.holder_private_key is None:
            raise ODISRecipeError(
                "this Agent has no holder key — register it with public_key_pem "
                "from new_holder_keypair() to use delegation"
            )
        if not self.wimse_uri:
            raise ODISRecipeError("holder_assertion needs the agent's wimse_uri")
        now = int(time.time())
        return pyjwt.encode(
            {
                "iss": self.wimse_uri,
                "sub": self.wimse_uri,
                "aud": audience,
                "iat": now,
                "exp": now + ttl_seconds,
                "jti": str(uuid.uuid4()),
            },
            self.holder_private_key,
            algorithm="ES256",
        )


# ---------------------------------------------------------------------------
# Layer 2 — delegation
# ---------------------------------------------------------------------------


def delegate(
    authn_url: str,
    *,
    subject_token: str,
    actor_assertion: str,
    scope: str,
) -> dict[str, Any]:
    """RFC 8693 token exchange — the ODIS Layer 2 Delegation Service.

    ``subject_token`` is the orchestrator's live credential (the authority being
    delegated). ``actor_assertion`` is the sub-agent's holder-of-key proof.

    The issued credential carries ``sub`` = the sub-agent, ``act.sub`` = the
    orchestrator, and ``delegation_depth`` one greater than the parent's.
    Granted scope is the intersection of *requested*, *what the orchestrator
    currently holds*, and *what the sub-agent is registered for* — so authority
    can only ever narrow (ODIS-L2-06).
    """
    r = httpx.post(
        f"{authn_url.rstrip('/')}/oauth2/token",
        json={
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": subject_token,
            "actor_token": actor_assertion,
            "scope": scope,
        },
        timeout=20,
    )
    if r.status_code >= 400:
        raise ODISRecipeError(f"delegation refused {r.status_code}: {r.text[:300]}")
    return r.json()


# ---------------------------------------------------------------------------
# Layer 1/3 — verification
# ---------------------------------------------------------------------------


def verify_local(authn_url: str, token: str) -> dict[str, Any]:
    """Verify a credential's signature offline against the published JWKS.

    Fast (no round-trip) but **not revocation-aware** — a revoked credential
    still verifies here until it expires. Use :func:`introspect` when the
    decision is security-critical.
    """
    import jwt as pyjwt
    from jwt import PyJWKClient

    jwks = PyJWKClient(
        f"{authn_url.rstrip('/')}/.well-known/jwks.json", cache_keys=True, lifespan=300
    )
    key = jwks.get_signing_key_from_jwt(token)
    return pyjwt.decode(
        token,
        key.key,
        algorithms=["RS256", "ES256"],
        options={"require": ["exp", "iat", "sub"], "verify_aud": False},
    )


def introspect(authn_url: str, token: str) -> dict[str, Any]:
    """Ask the issuer whether a credential is live right now (revocation-aware).

    RFC 7662. Many deployments require client authentication on this endpoint —
    including AuthN, which answers ``invalid_client`` without it. Callers should
    treat this as best-effort and fall back to asking the checkpoint. To revoke,
    use :meth:`ControlPlane.revoke_credential`: revocation is a governance
    action, and the administrative surface is the path that is always available.
    """
    r = httpx.post(
        f"{authn_url.rstrip('/')}/oauth2/token/introspect",
        json={"token": token},
        timeout=20,
    )
    if r.status_code >= 400:
        raise ODISRecipeError(f"introspection failed {r.status_code}: {r.text[:200]}")
    return r.json()


# ---------------------------------------------------------------------------
# Layer 3 — the governance checkpoint
# ---------------------------------------------------------------------------


@dataclass
class GuardOutcome:
    """What the checkpoint decided, and the identity context it decided on."""

    status: int
    decision: str | None
    reason: str | None
    signals: list[tuple[str, str]]
    identity: dict[str, Any] | None
    request_id: str | None
    receipt: dict[str, Any] | None
    raw: dict[str, Any]

    @property
    def denied(self) -> bool:
        return self.decision == "deny"

    @property
    def allowed(self) -> bool:
        return self.decision in ("allow", "modify")

    @property
    def no_policies(self) -> bool:
        """True when the tenant has no Cedar policies loaded.

        The checkpoint fails **closed** rather than waving the request through,
        which is correct — but it means the recipe cannot show an ``allow``
        until policies are enabled in Studio.
        """
        return self.status == 500 and "no policies loaded" in str(self.raw)


def guard(
    shield_url: str,
    token: str,
    *,
    content: str,
    action: str = "process_prompt",
    content_type: str = "prompt",
    session_id: str | None = None,
    tool: dict[str, Any] | None = None,
) -> GuardOutcome:
    """Call the ODIS Layer 3 governance checkpoint with a runtime credential."""
    body: dict[str, Any] = {
        "content": content,
        "content_type": content_type,
        "action": action,
        "session_id": session_id or f"odis-{uuid.uuid4().hex[:8]}",
    }
    if tool:
        body["tool"] = tool
    r = httpx.post(
        f"{shield_url.rstrip('/')}/v1/shield/guard",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=30,
    )
    try:
        raw = r.json()
    except ValueError:
        raw = {"body": r.text[:400]}
    return GuardOutcome(
        status=r.status_code,
        decision=raw.get("decision"),
        reason=raw.get("policy_reason"),
        signals=[
            (s.get("vulnerability_id", "?"), s.get("severity", "?"))
            for s in (raw.get("signals") or [])
        ],
        identity=raw.get("agent_identity"),
        request_id=raw.get("request_id"),
        receipt=raw.get("receipt"),
        raw=raw,
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class Config:
    authn_url: str
    shield_url: str
    account_id: str
    project_id: str
    owner_user_id: str
    registrar_token: str | None
    internal_secret: str | None
    internal_service: str

    @property
    def can_provision(self) -> bool:
        return bool(self.registrar_token or self.internal_secret)

    def control_plane(self) -> ControlPlane:
        return ControlPlane(
            self.authn_url,
            account_id=self.account_id,
            project_id=self.project_id,
            registrar_token=self.registrar_token,
            internal_secret=self.internal_secret,
            internal_service=self.internal_service,
        )


def load_config() -> Config:
    """Read configuration from the environment (and ``.env`` if present)."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:  # pragma: no cover - optional dependency
        pass
    return Config(
        authn_url=os.environ.get("HIGHFLAME_AUTHN_URL") or DEFAULT_AUTHN,
        shield_url=os.environ.get("HIGHFLAME_BASE_URL") or DEFAULT_SHIELD,
        account_id=os.environ.get("HIGHFLAME_ACCOUNT_ID") or "",
        project_id=os.environ.get("HIGHFLAME_PROJECT_ID") or "",
        owner_user_id=os.environ.get("HIGHFLAME_OWNER_USER_ID") or "cookbook-owner",
        registrar_token=os.environ.get("HIGHFLAME_REGISTRAR_TOKEN") or None,
        internal_secret=os.environ.get("HIGHFLAME_INTERNAL_SERVICE_SECRET") or None,
        internal_service=os.environ.get("HIGHFLAME_INTERNAL_SERVICE_NAME")
        or "highflame-admin",
    )


def unique(prefix: str) -> str:
    """A collision-resistant external_id for demo identities."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"
