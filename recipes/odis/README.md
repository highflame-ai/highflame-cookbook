# ODIS — the three layers, running

[ODIS](https://github.com/cosai-oasis/ws4-odis/blob/main/RFCs/ODIS.md) (CoSAI
WS4, *Open Delegated Identity for Agentic Systems*) specifies how an agent gets
an identity, how it receives authority from a human, and how that authority is
governed at the point of use. It organises this into three layers:

| ODIS layer | The question it answers |
| --- | --- |
| **1 — The Passport** | *What* software is running, and *which instance* is asking? |
| **2 — The Bridge** | *Who* is this agent acting for, and with how much of their authority? |
| **3 — The Router** | *What* may this specific request actually do, right now? |

This recipe exercises all three against a live Highflame deployment and prints a
requirement-by-requirement table. **Every row is produced by a real call** —
nothing is asserted from documentation.

> **This is not an ODIS conformance claim.** ODIS §8 reserves *Core*, *Extended*
> and *Safety* for a complete conformance target. This is a walkthrough with
> evidence: it reports **Meets** or **Partial** per requirement, names the
> limitation behind every Partial, and lists what it does not exercise at all.
> Several things it demonstrates are only partially satisfied — that is stated
> in the output, not buried here.

### The vocabulary, mapped

| ODIS term | In this recipe |
| --- | --- |
| Agent Registration Record (§6.1) | a ZeroID identity + its credential policy |
| Agent Runtime Credential (§6.2) | a short-lived JWT, verified against the issuer's JWKS |
| Delegation Record (§6.3) | an RFC 8693 exchange: `act` chain, `delegation_depth`, `mission_id` |
| Identity Context Object (§6.4) | Shield's `agent_identity` on every guard decision |
| Governance checkpoint (L3-02/06) | Shield: pre-Cedar scope ceiling, then policy |
| Revocation / kill switch (L1-12, L3-04/05) | credential revoke + identity deactivation, measured at the checkpoint |

> **Why this matters if you're rolling out agents.** The hard part of agent
> security is not blocking bad prompts; it's that an agent is a *new kind of
> principal*. It acts continuously, on someone's behalf, across systems that
> only understand users and service accounts. Give it a service account and you
> get an over-privileged, unattributable, un-revocable actor — the failure mode
> behind most agent incidents. ODIS names the three things you need to fix that.
> This recipe shows what each one costs to adopt: roughly 60 lines.

### Related: the ZeroID role-capability statement

There is a companion document scoped to **ZeroID alone** — an ODIS §8
role-capability statement mapping all 42 requirements to code and tests, with
the same Meets/Partial/Gap vocabulary, drafted for submission to the CoSAI WS4
workstream.

> **Not published yet** — it is an internal draft, so this is a forward
> reference rather than a link. Replace this paragraph with the URL once it
> lands (expected in the `zeroid` repo under `docs/odis/`).

The two are complementary, and where they disagree it is about **scope, not
facts**:

- It covers ODIS **Layers 1–2** in depth, at the authorization-server level, and
  declares Layer 3 out of role — an AS has no policy checkpoint, so L3-02 and
  L3-06 are honest **Gaps** there.
- This recipe is **platform-scoped**, so those same requirements are satisfied —
  by Shield, a different component. It also runs against the AuthN-embedded
  deployment rather than standalone ZeroID.

Read the statement for depth and for the requirements nothing here touches
(software attestation, bridge mode, presenter isolation, velocity limits). Read
this recipe to watch the parts that are implemented actually run.

Four capabilities the statement documents are now exercised here too, against
AuthN rather than standalone ZeroID. They live in **`odis_conformance.py`** —
the notebooks still walk the three layers only, so don't open `walkthrough.py`
expecting to demo DPoP:

| Capability | What the run shows |
| --- | --- |
| **DPoP** (L1-09) | `cnf.jkt` equals the RFC 7638 thumbprint of the agent's key; re-presenting the same proof is refused `invalid_dpop_proof` |
| **Attestation gating** (L1-11) | a policy requiring attestation refuses issuance twice — first on trust level, then on the missing attestation |
| **CIBA + RAR** (L2-02) | a human approves out of band; the token comes back carrying the exact `authorization_details` that were approved |
| **Delegation graph** (CC-01/02) | the lineage is queryable and outlives the credentials in it |

---

## Quickstart

```bash
cd recipes/odis
pip install -r requirements.txt
cp .env.example .env        # fill in the tenant + a provisioning credential
python odis_conformance.py  # the conformance table
python secure_agent.py      # the pattern to copy into your codebase
```

| File | What it's for |
| --- | --- |
| [`walkthrough.py`](walkthrough.py) | **[Marimo](https://marimo.io) notebook** — the three layers with narrative and live output. Best for demoing. |
| [`walkthrough.ipynb`](walkthrough.ipynb) | **The same notebook as Jupyter**, with outputs from a real run committed — readable without running anything. |
| [`odis_conformance.py`](odis_conformance.py) | Proves each ODIS requirement against your deployment. Use it as evidence, and in CI to catch regressions. `--json` for machine-readable output. |
| [`secure_agent.py`](secure_agent.py) | ~60 lines: an orchestrator, a sub-agent with less authority, and a checkpoint consulted before every action. **This is the artifact to copy.** |

### Showcasing it

```bash
marimo run walkthrough.py       # browser UI — the demo view
marimo edit walkthrough.py      # full editor, cells you can change live
python walkthrough.py           # executes every cell headlessly (CI-safe)
marimo export html walkthrough.py -o odis.html   # a static page to share
```

Prefer Jupyter? [`walkthrough.ipynb`](walkthrough.ipynb) is the same notebook,
with the outputs of a real run committed — so it reads end-to-end in GitHub's
viewer without a stack, an account, or a `pip install`.

```bash
jupyter notebook walkthrough.ipynb     # or just read it on GitHub
```

**One source, two formats.** The `.ipynb` is generated from `walkthrough.py`, so
they cannot drift. Regenerate after any change to the notebook:

```bash
marimo export ipynb walkthrough.py -o walkthrough.ipynb \
  --sort top-down --include-outputs
```

Because `--include-outputs` executes the notebook, the committed outputs are
real. Two consequences worth knowing: re-running produces different identifiers,
TTLs and timings (the semantics and status codes do not change), and the
outputs are checked for credential material before committing — a bootstrap key
or token in a committed cell would be a leak, not a demo.

The notebook makes the same real calls as the scripts — it imports
`odis_client.py` rather than reimplementing anything — and it retires the
identities it creates when it reaches the last cell.

[`odis_client.py`](odis_client.py) is the shared helper both use. It is plain
HTTP against documented endpoints — read it if you want to see exactly what goes
over the wire.

### Studio setup

1. **Create a project** and note its account + project IDs → `.env`.
2. **Provision a registrar identity** with the `nhi:manage` scope. Its token is
   what lets your pipeline register agents (`HIGHFLAME_REGISTRAR_TOKEN`).
3. **Enable at least one policy** under *Guardrails → Policies*. Without one the
   checkpoint fails **closed** — correct behaviour, but you'll see refusals
   rather than allows, and the conformance table will mark one check `SKIP`.

   A **permissive baseline in monitor mode is the right setting for a demo
   tenant**, and it does not weaken what this recipe demonstrates. Verified:

   | Request | With a permissive baseline policy loaded |
   | --- | --- |
   | correctly-scoped `process_prompt` | `allow`, naming the policy that permitted it |
   | `process_prompt` with only `tools:execute` | still `deny`, `insufficient_scope` (critical) |

   The second row is the important one. The scope ceiling is evaluated
   **before** Cedar, so `determining_policies` is `null` and the policy's mode
   is never consulted — a permissive or monitor-mode policy **cannot** waive it.
   That means one tenant configuration shows both the allow path *and* the
   Layer-2-attenuation deny, which is exactly what you want in a demo.

   The one thing you lose is the fail-closed demonstration: with policies
   loaded, the "no policy could decide" path no longer triggers, so that check
   flips to `SKIP` instead. The two are mutually exclusive by nature, and the
   harness reports whichever applies.

---

## What the conformance run proves

Output from a self-hosted deployment (abridged):

```
Layer 1 — The Passport (identity & attestation)
  [PASS] ODIS-CC-05     Registration is authorized and names an accountable owner
  [PASS] ODIS §6.1      Agent Registration Record carries the required governance fields
  [PASS] ODIS-L1-01     Agent authenticates with an ephemeral, verifiable credential
  [PASS] ODIS-L1-05     Credential lifetime is finite and bounded
  [PASS] ODIS §6.2      Runtime credential binds to the active registration record
  [PASS] ODIS-L1-09     Credentials can be holder-bound (proof-of-possession)

Layer 2 — The Bridge (delegation & access)
  [PASS] ODIS-L2-05     Delegation record carries an authenticated chain
  [PASS] ODIS-L2-06     Sub-agent authority is equal to or narrower than the parent's
  [PASS] ODIS-L2-01     Effective authority is the intersection, and an empty one fails closed
  [PASS] ODIS-L2-14     Delegation resolves the credential to an ACTIVE registration first
  [PASS] ODIS §6.3      Delegated credential never outlives its parent

Layer 3 — The Router (discovery & governance)
  [PASS] ODIS-L3-06     Checkpoint emits a structured identity-context object
  [PASS] ODIS-L3-02     Requested action is evaluated against the credential's authority
  [PASS] ODIS Core      Mediation fails closed when policy cannot be evaluated
  [PASS] ODIS-CC-01     Every decision is logged with a correlation identifier
  [PASS] ODIS-L3-04     Revocation propagates to the enforcement point within 300s
  [PASS] ODIS-L3-05     Immediate global de-provisioning via a single operation
```

---

## Layer 1 — The Passport

ODIS splits identity into a **durable governance record** and an **ephemeral
runtime credential**. Highflame's identity layer is ZeroID.

**The registration record** (ODIS §6.1) is created once, by a human or a
provisioning pipeline:

```python
record, bootstrap_key = cp.provision(
    external_id="research-orchestrator",
    owner_user_id="u_alice",          # ODIS-CC-05: an accountable human
    scopes=["tools:read", "tools:execute"],
    trust_level="first_party",
)
# record["wimse_uri"] -> spiffe://highflame.dev/acc_x/proj_y/agent/research-orchestrator
```

The identifier is a **SPIFFE/WIMSE URI** that embeds trust domain, tenant,
project, and agent — so the principal is self-describing, and ODIS's
`trust_domain` and tenancy fields are structural rather than metadata. The
platform **rejects registration without an owner**, which is what stops the
inventory rotting into a list of unattributable service accounts.

**The runtime credential** (ODIS §6.2) is what the agent actually presents:

```python
credential = agent.token()      # bootstrap key -> short-lived JWT
# ttl=3600s, sub=<the WIMSE URI>, jti=<unique>, status=active
```

The agent boots with a bootstrap key from your secret store and exchanges it for
a credential with a **finite, bounded lifetime** (ODIS-L1-01, ODIS-L1-05). The
credential carries the registration's `status`, `trust_level`, and granted
scopes, so a consumer validating it learns the governance state too — that
binding is ODIS-L1-03's "the running instance matches the claimed identity".

**Holder-of-key** (ODIS-L1-09). An agent can register an EC P-256 public key and
self-sign an assertion with the private half:

```python
private_key, public_pem = new_holder_keypair()   # private half never leaves the process
# ... register with public_key_pem=public_pem ...
assertion = agent.holder_assertion(audience=issuer)   # ES256, iss == sub == WIMSE URI
```

This is what makes a *stolen credential alone* insufficient — and it is a hard
requirement for delegation, below.

### Honest scope

ODIS-L1-02 (verify the software artifact) and ODIS-L1-03 in its full form
(platform-attested workload identity) are where an ODIS-conformant deployment
does the most integration work, and where you should read the fine print.

The identity layer has an attestation model with three proof types, and they are
**not equally real today**:

| Proof type | Status |
| --- | --- |
| `oidc_token` | **Implemented.** A real verifier validates the token against the upstream issuer's JWKS — GitHub Actions, GCP Workload Identity, Kubernetes projected service-account tokens, AWS IAM. |
| `image_hash` | **Not implemented.** A dev stub exists purely to exercise demo flows, and it verifies *anything*. It is only registered when an explicit unsafe-dev flag is on, which production deployments leave off — so the proof type is simply unavailable there. |
| `tpm` | **Not implemented**, same as above. |

**This recipe exercises none of them**: it registers agents at a *declared*
trust level. So treat `trust_level: first_party` in the output above as an
assertion by whoever ran the provisioning call, not as evidence about the
running software.

The practical guidance: if your workloads run in CI or on a cloud platform, wire
`oidc_token` attestation — it's real, and it's the cheapest way to make
`trust_level` mean something. Do not build policy that depends on `image_hash` or
`tpm` until they land. The conformance table has no `ODIS-L1-02` row for exactly
this reason.

---

## Layer 2 — The Bridge

This is the layer most agent stacks don't have at all, and the one that decides
whether multi-agent systems are containable.

Delegation is RFC 8693 token exchange. The orchestrator presents its live
credential as the `subject_token`; the sub-agent presents a holder-of-key
assertion as the `actor_token`:

```python
delegated = delegate(
    authn_url,
    subject_token=orchestrator_credential,
    actor_assertion=sub_agent.holder_assertion(audience=issuer),
    scope="tools:read",
)
```

The issued credential is a **delegation record** (ODIS §6.3):

```
sub              = the sub-agent's WIMSE URI      (who is acting)
act.sub          = the orchestrator's WIMSE URI   (on whose behalf)
delegation_depth = parent + 1                     (how far from the human)
mission_id       = inherited from the parent      (ODIS task_id — one id per task tree)
```

**Authority can only narrow.** Granted scope is the three-way intersection of
*requested* ∩ *what the orchestrator currently holds* ∩ *what the sub-agent is
registered for*. Observed:

```
orchestrator holds     : tools:read tools:execute tools:write
sub-agent registered   : tools:read tools:execute
requested              : tools:read tools:write
granted                : tools:read              <- tools:write dropped
requested tools:write  : refused, invalid_scope  <- empty intersection fails closed
```

That is ODIS-L2-06 and ODIS-L2-01. It's worth being precise about *why* it
matters: the orchestrator genuinely holds `tools:write`, and still cannot pass
it on, because the sub-agent isn't registered for it. **A compromised or
prompt-injected orchestrator cannot escalate its children.** The ceiling is in
the registration, not in the calling code — so it holds even when the calling
code is the thing that's wrong.

Two further properties the harness checks:

- **Delegation resolves to an *active* registration first** (ODIS-L2-14).
  Deactivate the sub-agent and the exchange is refused — `actor identity is
  suspended or deactivated`. Authority is never granted to a principal whose
  governance record has been withdrawn.
- **A child never outlives its parent.** The delegated credential's `exp` is
  clamped to the subject's, so a late exchange can't mint a long-lived child
  from an expiring parent.

### Honest scope

- The actor assertion is **replayable within its lifetime** — there's no
  consumed-`jti` store on this path. Keep assertion TTLs short (the helper uses
  300s). ADR 0010 mandates single-use `jti` tracking for the ID-JAG admission
  grant specifically; that protection does not currently extend to the
  NHI-delegation actor token.
- ODIS's richer `Delegation Record` fields — `originating_authorization_ref`,
  `attenuation_profile_ref`, explicit `constraints` — are not separate fields
  here. The equivalent information lives in the token claims and the credential
  record; a strict ODIS-Extended reading would want them named explicitly.

---

## Layer 3 — The Router

The governance checkpoint is Shield. Every action is evaluated *before* it
happens, against the identity that is asking.

**A structured identity-context object** (ODIS-L3-06) is what the checkpoint
decides on, and it returns it to you:

```json
{
  "external_id": "summariser-49fee84f",
  "identity_type": "agent",
  "sub_type": "tool_agent",
  "trust_level": "first_party",
  "status": "active",
  "auth_method": "api_key",
  "name": "summariser"
}
```

This is the practical difference from a guardrail bolted onto a prompt: the
decision is about *this principal doing this thing*, not about the text. Policies
can key on trust level, delegation depth, ownership, or credential age — not just
on content. (`auth_method` reports the grant used to obtain the credential.)

**Layer 2's attenuation is enforced here, before policy.** Scopes are a hard
ceiling checked *ahead of* policy evaluation:

```
token scopes : tools:read
action       : call_tool   (requires tools:execute)
->  deny  "token missing required scope \"tools:execute\" for action \"call_tool\""
    signal: insufficient_scope (critical)
```

The ordering is the point. A missing scope is not a policy opinion that a
misconfigured rule could waive — it's a ceiling. The vocabulary:

| Scope | Grants |
| --- | --- |
| `tools:read` | Read files; feed prompts/context to the model |
| `tools:write` | Create, modify, delete files |
| `tools:execute` | Invoke MCP tools, IDE tools, shell commands |
| `tools:network` | Outbound HTTP; remote MCP servers |
| `tools:agent` | Spawn or delegate to sub-agents |
| `tools:vcs` | Commit, branch, push, open PRs |

| Action | Required scope |
| --- | --- |
| `process_prompt`, `read_file` | `tools:read` |
| `call_tool` | `tools:execute` |
| `write_file` | `tools:write` |
| `connect_server` | *(none — per-tool scopes gate the actual operations)* |

**Fail-closed mediation.** With no policy able to decide, the checkpoint refuses
rather than defaulting to allow. In the run above, a tenant with no policies
loaded returns a hard error instead of an `allow` — which is why the recipe's
Studio setup step matters, and why you should be suspicious of any agent
guardrail that gets *quieter* when misconfigured.

**Revocation and the kill switch** (ODIS-L3-04, ODIS-L3-05). ODIS allows 300
seconds for revocation to propagate inside a trust domain. Measured at the
enforcement point:

```
revoke a single credential      -> checkpoint rejects it in < 1s
deactivate the identity (1 call) -> bootstrap key can no longer mint,
                                    AND already-issued credentials stop working
```

The second is the one to internalise. Revoking a token is not enough — a
surviving bootstrap key would just mint a new one, making the offboarding
cosmetic. Deactivating the identity closes both.

**One caveat worth knowing.** Offline JWKS verification is *not*
revocation-aware: a revoked credential still passes a local signature check
until it expires. That's the correct trade (no network call on a hot path), but
it means **local verification is not an authorization decision**. Route
security-critical checks through the checkpoint or introspection. The harness
reports this explicitly rather than letting you discover it in production.

### Honest scope

- **Signed decision receipts** are supported (a tamper-evident, offline-
  verifiable receipt per decision, signed with a workload-attested ephemeral
  key) but were **disabled in this run** — the conformance row reads `receipt
  signing disabled`. Enable receipt signing if you need ODIS-CC-06's
  "authoritative audit anchor" property, and re-run.
- ODIS-L3-03 (per-agent rate limits) and Layer 3 **tool/service discovery** are
  not exercised here.

---

## Deployment shapes, and one wrinkle

Highflame's identity layer ships two ways, and they mount their admin API
differently:

| Shape | Admin prefix | Token endpoint |
| --- | --- | --- |
| ZeroID embedded in AuthN | `/` (host root) | `/oauth2/token` |
| ZeroID standalone | `/api/v1` | `/oauth2/token` |

`odis_client.py` probes for the prefix, so the identity-plane calls (register,
issue, list, revoke, retire) run unchanged against either — both shapes are
verified. The *full* recipe needs one more thing: your checkpoint has to trust
that issuer, or Layer 3 rejects every credential. See the note below.

### Two provisioning surfaces, and they are not interchangeable

Which credential you provision with also decides *which API you may call*:

| Credential | Surface | Register | Deactivate |
| --- | --- | --- | --- |
| `HIGHFLAME_REGISTRAR_TOKEN` (`nhi:manage`) | `/agents/*` | `POST /agents/register` — creates identity **and** bootstrap key atomically | `POST /agents/registry/{id}/deactivate` |
| `HIGHFLAME_INTERNAL_SERVICE_SECRET` | `/identities`, `/api-keys` | `POST /identities` then `POST /api-keys` | `PATCH /identities/{id}` |

A registrar token is deliberately confined to the registry surface — it gets
**403** on `/identities` and `/api-keys`, by design. `odis_client.py` branches on
this; both paths are exercised and both produce an identical conformance result.

One sharp edge on `/agents/register`: it has **no `owner_user_id` field**. The
owner is derived from **`created_by`**. Omit it and registration fails with
`owner_user_id is required` — naming a field that endpoint does not accept.

Two more things to know:

- **`highflame.zeroid.ZeroIDClient` targets one shape at a time.** As of SDK
  **0.3.23** it uses host-root paths and defaults to SaaS, so it drives the
  AuthN-embedded plane and returns 404 against a standalone ZeroID on `/api/v1`.
  (Earlier versions did the opposite.) This recipe uses its own thin HTTP helper
  for two reasons: it probes for the prefix and so works against both, and raw
  HTTP lets you read the wire format a conformance exercise is really about.

  **If you are building on the SDK rather than reading this recipe, use it** —
  0.3.23 ships `generate_keypair()` and `build_actor_assertion()`, so the
  holder-of-key mechanics this recipe spells out by hand are one call each:

  ```python
  from highflame.zeroid import ZeroIDClient, generate_keypair, build_actor_assertion

  private_pem, public_pem = generate_keypair()
  sub = client.agents.register(name="summariser", external_id="summariser",
                               created_by="u_alice",        # this becomes owner_user_id
                               allowed_scopes=["tools:read"], public_key_pem=public_pem)
  assertion = build_actor_assertion(wimse_uri=sub.agent.wimse_uri,
                                    private_key_pem=private_pem, audience=issuer)
  delegated = orchestrator.tokens.delegate(actor_token=assertion, scope="tools:read")
  ```
- **Your checkpoint and your issuer must be the same deployment.** Shield's JWKS
  is pinned to one issuer; a credential from a different ZeroID is rejected with
  `invalid or expired token`, which reads like a bad token and is really a
  misconfiguration.

---

## Adoption order

If you're securing an agent rollout, the layers pay off in a specific order:

1. **Layer 1 first, and only Layer 1.** Give every agent its own identity with a
   named owner and a short-lived credential. This alone converts "an
   unattributable service account" into "a principal you can see, attribute, and
   turn off". Cheapest step, largest single gain.
2. **Layer 3 next.** Put the checkpoint in front of actions and enable one
   policy. You now have a decision per action, with the identity attached, and a
   correlation id for the audit trail.
3. **Layer 2 when you have more than one agent.** The moment an orchestrator
   spawns sub-agents, monotonic attenuation is what keeps a compromise from
   spreading. Before that it's ceremony; after that it's the containment
   boundary.
4. **Attestation and receipts last.** Real software/workload attestation
   (Layer 1's harder half) and signed receipts are what move you from "we have
   identity" to "we can prove what happened to an auditor".

The trap worth naming: it is tempting to start at Layer 3, because content
guardrails demo well. But a checkpoint with no identity underneath it can only
decide about *text*. Layer 1 is what lets it decide about *principals* — which is
the whole reason ODIS puts the Passport first.

---

## CI

`smoke_test.py` follows the cookbook contract (`0` pass, `1` fail, `2` skip) and
is picked up by [`.github/workflows/smoke.yml`](../../.github/workflows/smoke.yml).
A tenant-side gap (no policies enabled) is a `SKIP`, not a failure; a genuine
regression in any ODIS check reds the build.

**Every script retires the identities it creates**, in a `finally`, so a failed
run cleans up too. A conformance pass provisions seven agents and retires seven;
`total` grows, `active` does not. This matters more than it sounds: nightly CI
would otherwise leave a few thousand live agent identities a year in the canary
tenant — which is precisely the unattributable-service-account sprawl the recipe
exists to argue against.

Retirement here is a *soft* retire: the identity is deactivated and its
credentials revoked, but the record survives for audit. That is the Retire stage
of the identity lifecycle, and it is the step most rollouts skip.

> **If you list identities yourself**, note that `GET /identities` pages at 20
> and ignores a larger `limit` — read `total` and walk `offset`, or you will
> quietly audit only the first page. (The SDK's `identities.list()` exposes no
> pagination parameters at all, so it returns the first page only.)

---

## Reference

- [ODIS RFC](https://github.com/cosai-oasis/ws4-odis/blob/main/RFCs/ODIS.md) — CoSAI WS4
- RFC 8693 (token exchange) · RFC 7523 (JWT bearer) · RFC 9449 (DPoP) · RFC 8707 (resource indicators)
- [SPIFFE](https://spiffe.io/) — the WIMSE URI format
- [MCP Enterprise-Managed Authorization](https://modelcontextprotocol.io/extensions/auth/enterprise-managed-authorization) — the admission flow the identity plane advertises (`urn:ietf:params:oauth:grant-profile:id-jag`)
- Full platform docs: [docs.highflame.ai](https://docs.highflame.ai)
