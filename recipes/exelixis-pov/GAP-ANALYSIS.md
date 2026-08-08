# Exelixis PoV — gap analysis & engineering backlog

This is the engineering companion to the [Exelixis PoV cookbook](README.md).
Every use case that is not fully supported becomes a scoped work item here: what is missing, the repo it lands in, the capability-spec entry it needs, a rough size, and whether it blocks the PoV or is a fast-follow.
It exists so the "reconnect to discuss logistics" conversation starts from a concrete, prioritized list instead of a whiteboard.

**Ground rule for the whole PoV:** nothing marked `planned` in `highflame-architecture/capabilities.yaml` is presented to the client as shipped.
Several of these gaps are "the code is further along than the spec" — where that is true it is noted, but the spec status governs what we _claim_.
Any gap promoted to "supported" must land its verifying regression test first (per INV-GOV-001).

---

## Priorities at a glance

| Tier                                             | Gaps                                                                               | Why                                                                                           |
| ------------------------------------------------ | ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| **P0 — do before the PoV**                       | Copilot connector claim (done), fail-closed posture decision, policy-pack pre-load | Avoid an avoidable demo failure or an over-claim in the room                                  |
| **P1 — the headline gaps the client will probe** | G-UC8 (human→agent revocation), G-UC1 (shadow-in-traffic), G-UC9 (semantic drift)  | These are the differentiated asks; a credible roadmap answer matters even where we can't demo |
| **P2 — real, scoped, fast-follow**               | G-UC6, G-UC7 (A2A), G-UC11, G-UC12a/b, G-UC10, G-UC4                               | Each closes a "partial" into a "supported"; independently shippable                           |
| **P3 — hygiene & spec drift**                    | doc drift, stale TTLs, capability-spec catch-up                                    | Low effort, high credibility with a technical buyer                                           |

Size key: **S** ≈ days, **M** ≈ 1–2 weeks, **L** ≈ 3+ weeks / cross-team.

---

## P0 — before the PoV

### FIXED · Copilot Studio connector claim

The `agent-governance` recipe advertised a "Copilot Studio" IdP connector that does not exist (the Studio tile 400s).
**Fixed in this PR** — corrected to the four real connectors (Entra, Okta, Google Workspace, Google Agent Engine).
There is a matching bug in the product: Studio's `ConnectionsList` still renders a clickable Copilot tile.
→ **`highflame-studio`** (`packages/registry`), remove or gate the `copilot` provider. **S.**

### DECISION · fail-closed posture on the gateway

Firehog → Shield defaults to **fail-open** (a Shield outage lets traffic through with a warning), including on dev1.
For a security PoV whose ask is "checked before execution, _always_," this should be flipped.
→ **`highflame-cloud`** (`app-config/highflame-firehog/config.yaml`), set `shield.fail_closed: true`.
The enforcement code already exists; this is a one-line config change plus a blast-radius decision. **S.**
Disclose the current default either way.

### CHECKLIST · pre-load the policy packs

Shield only runs a detector if an active policy references its signal.
Each track README names the packs it needs; load them (enforce or monitor) in the PoV project before the call. **S.**

---

## P1 — headline gaps

### G-UC8 · Human deactivation → agent denial _(the #1 gap)_

**Use case 8.** An agent acting for a deactivated/revoked human is not automatically denied.
The revocation _mechanism_ is fully built (revoke an identity → its whole delegation tree dies in <5s); the missing piece is the _trigger_ from the human's IdP lifecycle. Four small, independent pieces:

| Piece                                                                                                            | Repo                                        | Capability                                        | Size |
| ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------- | ------------------------------------------------- | ---- |
| Handle `user.deleted` / `user.updated(locked)` / `organizationMembership.deleted` Clerk webhooks                 | `highflame-studio` (or a new Admin ingress) | new CAP-IDN-\*                                    | S    |
| SCIM 2.0 receiver for Okta/Entra human lifecycle                                                                 | `highflame-admin` (tenancy)                 | CAP-TEN-\* (ADR 0015 defines the writer contract) | M    |
| `revoke_credentials_by_owner(owner_user_id)` — mirrors the existing cascade SQL                                  | `zeroid`                                    | new CAP-IDN-\*                                    | S    |
| Backstop: project `principal.status` / `owner_status` into Cedar so a policy can `forbid when owner deactivated` | `highflame-shield` + `highflame-policy`     | new INV-ENF-\*                                    | M    |

**This is an integration, not a new enforcement engine** — that framing matters to the client.
Recommend building at least pieces 1 + 3 for the PoV so the end-to-end "deactivate the human → the agent's next call 401s" story is demonstrable. **Overall M.**

### G-UC1 · Shadow-agent detection from traffic

**Use case 1.** We discover agents the IdP already knows about; we do not detect an agent seen only in gateway traffic that is in no registry.
Design of record exists — **ADR 0027 (Proposed)** — but is not built. Needs: a canonical identity attribute emitted on every span, a resolver that joins `hf_events` traffic to the ZeroID registry, and an "unresolved / unregistered principal" surface in Observatory/Studio.
→ **`highflame-observatory`** (resolver + surface) + **`highflame-shield`/`highflame-firehog`** (emit the attribute) + **`highflame-collector`** (span → column).
No capability ID yet; needs one. **L.**
Adjacent, smaller: the MCP-coverage "shadow" view exists but the classifier runs name-heuristic only — wiring its RFC 9728 prober is **S** and makes that one screen real.

### G-UC9 · Semantic objective-drift detection

**Use case 9.** A redirect phrased as an injection is caught; a redirect phrased as a benign topic change is not.
`CAP-DET-002` (**planned**) is the embedding-based intent-drift detector: `1 − cosine(embed(original_request), embed(current_action))` with cumulative EMA, emitting `intent_drift_score` / `intent_drift_exceeds_threshold` into Cedar.
The anchor (`session_original_request`) is already captured and projected; the comparator is the work.
→ **`highflame-shield`** (`internal/detector/ml/`, use the `add-detector` skill) + an embedding endpoint in **`javelin-models`** + Cedar keys in **`highflame-policy`** + a session-snapshot EMA field (a chain-version migration — the sharpest edge) + a default `defer/alert` policy.
`CAP-DET-002` + AARM R7. **L.**

---

## P2 — close a "partial" into "supported" (fast-follow)

### G-UC4 · Per-task (RAR) credentials

Short-lived is supported; task-scoping is coarse OAuth scope.
RFC 9396 Rich Authorization Requests exist but only on the CIBA (human-approval) endpoint, not the machine token endpoint.
→ **`zeroid`** (`feat/rar-token-side` branch exists, not merged) + `highflame-shield` enforcement. Also file the two `planned` scope-enforcement caps (CAP-IDN-008 silent-narrowing→reject; CAP-IDN-009 read/write operation scopes). **M.**

### G-UC6 · Delegation chain completeness

Three independent edges:

- Observatory can't filter/group by delegation fields (they're in a span-attribute map). → **`highflame-observatory`** ADD COLUMN + MV (precedent: `migrations/020_owner_user_id.sql`) + ViewQL dimensions. **M.**
- The MCP gateway drops `X-Agent-*` delegation headers (firehog#372). → **`highflame-firehog`**. **M.**
- Nested `act` claim (full chain in one token) — optional; `mission_id` reconstruction is a defensible alternative. → **`zeroid`**. **M.**

### G-UC7 · A2A-native authorization

A2A hops are checked only as a coerced `process_prompt` text scan.
Needs an A2A-native Cedar action (`a2a_send`/`a2a_receive`, or land ADR 0012's `AgentOps::` unification), scanning of the agent-card fetch / task SSE stream / non-text parts, and A2A identity keys in the AIGateway schema so the shipped A2A templates apply.
→ **`highflame-policy`** + **`highflame-shield`** + **`highflame-firehog`**. No A2A capability exists yet — needs a spec entry. **L.**
Also retire or implement the dead AuthZ PDP `/authorize` arm (**`highflame-authz`** or `highflame-firehog`). **S.**

### G-UC10 · Redactable secrets & file redaction

Secrets are block-only; a `mask` effect on a secrets rule silently degrades to allow.
→ **`highflame-shield`** (`merge.go` + emit secret offsets from `secrets.go`). **M.**
Files are blocked-not-redacted (firehog#369). → **`highflame-firehog`**. **M.**
Also: `RedactionEntry.Original` carries the raw PHI value on the audit response — gate it behind a flag before a HIPAA review asks. **`highflame-shield`**. **S.**

### G-UC11 · Custom-pattern UX & merge semantics

Engine supported; two edges:

- No Studio UI for custom regex (API-only today). → **`highflame-studio`** (`DetectorConfigPanel`). **M.**
- The custom-pattern write **replaces** the built-in set instead of merging — a footgun. → **`highflame-shield`** (`pii_regex.go`, add `extends_defaults`/`custom_entries`). **S.**
- Studio's PII panel exposes 10 of 70+ types and deploying it _narrows_ the detector — fix the panel to drive off the live detector list. → **`highflame-studio`**. **S.**
- Keyword UI writes `match_mode`/`case_sensitive`/`severity` that Shield ignores — implement or disable them. → **`highflame-shield`** + **`highflame-studio`**. **S.**

### G-UC12a · Project `indirect_injection_score` on the gateway path

The signal is only projected for Overwatch/Sentry, so the shipped gateway supply-chain template no-ops.
→ **`highflame-shield`** (projector/scheduler). **S.**

### G-UC12b · Scan MCP tool descriptions at `tools/list`

The gateway applies an allowlist at `tools/list` but never scans descriptions; the detector exists, the call-site doesn't.
→ **`highflame-firehog`** (`list_tools_impl`). **M.**
Related: **INV-DET-002** (server→client request inspection) — chokepoint merged, classifier (`shield#377`) in review; finish and flip the spec status. **`highflame-shield`**. **S.**

---

## P3 — hygiene & spec drift (low effort, high credibility)

- **Stale TTL docs:** `highflame-studio/auth.md` and `highflame-authn/README` claim a 15-minute `api_key` TTL; the real value is 3600s. A client who decodes a token will catch this. → **`highflame-studio`** + **`highflame-authn`**. **S.**
- **NHI span-attribute doc drift:** `non-human-identity.md` documents `hf.nhi.*` attribute names that don't exist (real names are `hf.act_sub`, `hf.delegation_depth`, `hf.agent_wimse_uri`, `hf.mission_id`) and claims typed columns that aren't there. → **`highflame-architecture`**. **S.**
- **Stale discovery docs:** an advertised `GET /v1/admin/discovery/agents` endpoint is retired; the MCP-typing claim overstates a heuristic-only classifier. → **`highflame-studio/apps/docs`**. **S.**
- **Capability-spec catch-up:** several entries are `planned` while the code visibly works (`CAP-DSC-001/002/003` discovery, parts of `CAP-IDN-012/013`, `CAP-DET-001`). Reconcile with eng and flip where a verifying test exists. `CAP-TEN-006` is referenced in code but absent from the spec. → **`highflame-architecture`**. **S.**

---

## What to build first (recommendation)

If the goal is the strongest possible PoV with bounded engineering:

1. **G-UC8 pieces 1 + 3** (Clerk webhook + revoke-by-owner) — turns the single biggest gap into a live end-to-end demo. **M.**
2. **G-UC12a** (project `indirect_injection_score` on the gateway) and **G-UC11** merge-not-replace + PII-panel fix — small changes that make three "partials" demo cleanly. **S each.**
3. **P0 fail-closed decision** + policy-pack pre-load. **S.**
4. Everything else (G-UC1, G-UC9, G-UC7, G-UC6) → present as a credible, specced roadmap with the ADRs that already exist behind them. These are real features, not hand-waving, and saying so honestly is stronger than pretending they're done.

Each item above should go through `/feature-prep` (capability entry first, tests in the right tier) before implementation, so the spec stays a leading indicator and the regression suite stays high-signal.
