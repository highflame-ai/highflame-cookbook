# 01 · Identity Orchestration — discover, identify, delegate, scope, revoke, trace

**The value:** _"Our teams spin up AI agents faster than we can track them. Each one is a new identity nobody issued, owns, or can revoke. We want to discover every agent, give each a unique identity with a real owner, make sub-agents unable to out-privilege their parent, hand out short-lived credentials, and — when we pull the plug on one — have the whole delegation tree collapse, all traceable back to a human."_

This track covers use cases 1–6.
The runnable proof — [`identity_lifecycle.py`](identity_lifecycle.py) — proves the properties a single service key can prove: unique identity (UC2), short-lived and scope-limited credentials (UC4), and revocation ahead of expiry (UC5).
Discovery (UC1), sub-agent attenuation (UC3), and the delegation chain (UC6) need two registered identities, so they run from Studio; the exact click-path is below.

| UC  | Claim                                                   | Verdict      | Proof                                                                                     |
| --- | ------------------------------------------------------- | ------------ | ----------------------------------------------------------------------------------------- |
| 1   | Discover in-house, third-party, **and shadow** agents   | 🟡 Partial   | Studio → Registry (IdP connectors). Shadow-in-traffic **not** built.                      |
| 2   | Unique identity per agent, not a shared key             | 🟢 Supported | `identity_lifecycle.py` → the token's `sub` + a DB uniqueness constraint                  |
| 3   | Sub-agents cannot exceed the parent's authority         | 🟢 Supported | Studio → ZeroID → delegate; over-broad scope → `400 invalid_scope`                        |
| 4   | Short-lived, task-scoped credentials                    | 🟡 Partial   | `identity_lifecycle.py` → 1h TTL + scope ceiling; task-scoping is coarse                  |
| 5   | Revoke parent → collapse the tree                       | 🟢 Supported | `identity_lifecycle.py` (single token) + Studio (full cascade)                            |
| 6   | Traceable human → orchestrator → sub-agent → tool chain | 🟡 Partial   | Studio → Observatory → Audit; gateway now forwards to Shield, Observatory columns pending |

---

## Run the proof

```bash
cd recipes/exelixis-pov
cp .env.example .env          # set HIGHFLAME_API_KEY (a zid_sk_ service key)
pip install -r requirements.txt
python 01-identity-orchestration/identity_lifecycle.py
```

You will see the token's claims (the UC2 proof), a one-hour expiry and a read-only token that Shield refuses a write (UC4), and a revoked token being denied on its next call (UC5).

---

## UC2 · Unique identity — supported

Every agent's token carries a `sub` that is _its own_ WIMSE URI:

```
spiffe://<trust-domain>/<account_id>/<project_id>/agent/<external_id>
```

Uniqueness is not a convention — it is `UNIQUE (account_id, project_id, external_id)` in Postgres, and registering the same `external_id` twice returns `409 Conflict`.
The token also carries `owner_user_id` (the accountable human) and a `jti` (the per-credential revocation handle).

**The honest edge:** there is one raw-API path that can still bind a key to a shared, product-level service identity (create a key with a `product` but no `identity_id`).
Studio never does this — it always binds a key to a specific identity.
Closing the raw-API path is tracked as G-UC2 in [`GAP-ANALYSIS.md`](../GAP-ANALYSIS.md).

## UC3 · Sub-agents cannot out-privilege the parent — supported

Attenuation is enforced **server-side at the moment a delegated token is issued**.
A child token's scopes are the intersection of what was requested, what the parent actually holds, and what the child's own policy allows.
Ask for a scope the parent never held and the exchange returns `400 invalid_scope` — even if the child's own policy would permit it.

**Studio click-path:**

1. **Studio → ZeroID → Start.** Register an **orchestrator** and mint its token with, say, `tools:read tools:execute`.
2. Register a **sub-agent** — the wizard generates its keypair in-browser and enrolls the public key.
3. Delegate. The **scope-attenuation funnel** shows each parent scope kept or dropped: _"1 of 2 scopes attenuated — sub-agent receives only [tools:read]"_.
4. **The escalation test:** give the sub-agent's policy `allowed_scopes: [tools:read, tools:write]`, then request `tools:write` — a scope the parent never held. → `400 invalid_scope`, _"requested scopes are not available for delegation."_

Run step 4 twice — once where the child's _own_ policy permits the scope. It still fails. That is the difference between "the child is configured narrowly" and "the child _cannot_ exceed the parent."

## UC4 · Short-lived, task-scoped — partial

**Short-lived: supported.** The default token TTL is one hour, clamped down by the identity's and the key's own expiry — a 20-minute key can never mint a one-hour token.
Revocation (UC5) beats expiry entirely.

**Task-scoped: partial.** Scoping today is coarse OAuth scope — a read-only credential (`mcp:read`) is refused any write-class action (`call_tool`, `write_file`) at Shield's scope ceiling, _before_ detectors and Cedar, with a signed receipt.
The script proves exactly this.
What does **not** exist on the machine token endpoint is _per-task_ authorization — RFC 9396 Rich Authorization Requests ("this agent may call `transfer_funds` for $500 from account X").
That typed grant exists, but only behind a human CIBA approval, not for autonomous agents.
Tracked as G-UC4.

## UC5 · Revoke parent → collapse the tree — supported

The script revokes a token and shows the next call returning `401 token has been revoked`.
For a **parent** identity, revocation cascades: a single atomic recursive `UPDATE` walks the `parent_jti` edges and revokes the parent and every delegated descendant at once — the whole subtree dies, regardless of which identity minted the children.
Triggers: revoke the credential, deactivate the identity in Studio → Registry, or raise a critical CAE signal.

**Latency, stated precisely** (say this before the client asks):

- At the credential store: **atomic and instant.** Any ZeroID-side check (introspection, further delegation) sees it immediately.
- At the enforcement point (Shield): **sub-second in steady state, SLO < 5s** — propagation is Redis pub/sub.
- **Cold-start gap:** a Shield replica that (re)connects _after_ the revocation was published will honour the token until its natural expiry (default 1h). This is a documented limitation with a named fix; see G-UC5.

## UC6 · Traceable chain — partial

Every hop is recorded in two independent stores and rendered in the product.

**Studio click-path:** run a delegated tool call, then **Studio → Observatory → Audit** → select the session.
The header renders _"Agents in this session" → "Root orchestrator" → "Delegation chain"_ as `orchestrator → sub-agent` chips, with the tool and MCP calls nested under the sub-agent that made them.
The identity side complements it: **Studio → Registry → Graphs** walks `parent → child` with the scope attenuation on each edge.
Observatory answers _"what did this chain do?"_; ZeroID answers _"what was this chain allowed to do?"_

**The honest edges:**

- The JWT `act` claim is **single-hop** (`{sub, iss}`), not a nested chain — one token proves one hop; the full tree is reconstructed via `mission_id` on the server, not carried in the bearer token.
- Observatory keeps the delegation fields in a span-attribute map, so you can _read_ them per event but cannot yet _filter/group_ by `mission_id` or `delegation_depth`.
- A tool call proxied through the **MCP gateway** now forwards the `X-Agent-*` delegation headers to Shield (firehog #372/#528, merged), so the Shield decision on the gateway path carries `act_sub`/`mission_id`/`delegation_depth` — the earlier "demo the direct path only" caveat no longer applies to the Shield decision. Two narrower edges remain: the gateway does not relay the chain onward to the _upstream_ MCP server, and Observatory keeps these fields in a span-attribute map rather than typed columns (so you can read them per-event but not filter/group by them). Tracked as G-UC6a.

## UC1 · Discover every agent — partial

**Supported:** Highflame connects to the IdP you run — **Microsoft Entra, Okta, Google Workspace, Google Agent Engine (Vertex AI)** — and discovers the agents and OAuth apps already operating there.
**Studio click-path:** Registry → Connectors → add a connector → **Sync now** → Registry → Inventory (filter by origin/status) → Registry → **Unmanaged** to adopt ownerless agents (ranked by blast radius) with an accountable owner.

**The honest edges:**

- **Shadow agents seen only in traffic** — an agent hitting the gateway that is in no registry — are **not** detected yet. Today "shadow" means an OAuth app the IdP knows about but nobody owns, not an unknown agent observed on the wire. The design exists (ADR 0027); it is not built. Tracked as **G-UC1** and it is one of the three headline gaps for this PoV.
- Coverage is Azure + GCP IdPs today; **there is no AWS connector.**
- The MCP-coverage "shadow" view exists but shows zero on a tenant with no discovered MCP servers.

Do **not** demo an AWS-origin agent or claim shadow-in-traffic detection.

---

## Verify

```bash
python 01-identity-orchestration/smoke_test.py
```

Confirms a token mints, its subject is a WIMSE URI with an owner, and a revoked token is denied.
