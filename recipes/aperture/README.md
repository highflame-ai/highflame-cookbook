# Highflame + Tailscale Aperture

[Tailscale **Aperture**](https://tailscale.com/docs/aperture) is the AI gateway that routes
your tailnet's LLM traffic with Tailscale's identity layer attached. **Highflame plugs into
Aperture as a `pre_request` guardrail** → Cerberus → Shield: every prompt and tool
declaration is evaluated *before* it reaches the model provider, with the developer's
identity on it. On a policy hit, Aperture relays a **clearly branded Highflame message** —
not a generic error.

This integration is **agent-agnostic**: it covers every Aperture-routed coding agent —
`aperture_claude` (Claude Code), `aperture_codex`, `aperture_cline`, `aperture_gemini_cli`,
`aperture_roo_code`. The demo drives **Claude Code**, but the same recipes secure all of them.

```
Agent (Claude Code, …) ──▶ Tailscale Aperture ──pre_request guardrail──▶ Highflame Cerberus ──▶ Shield
                                 │                                     allow / block / modify (+message)
                                 └──◀──── {"action":"block","message":"Highflame Security …"} ◀────┘
```

> **Two-repo demo.** This folder is the *guide*; the *stage* is a separate, deliberately
> insecure repo — [`highflame-demo-vault`](https://github.com/highflame-ai/highflame-demo-vault) —
> full of planted (fake) secrets, PII, and injection payloads. Wire up Aperture once,
> open the vault in your agent, reproduce every scenario.

---

## One-time setup

Highflame has a first-class **Tailscale Aperture** integration in Studio → **Code Agents**.
Full steps: [docs.highflame.ai/integrations/tailscale](https://docs.highflame.ai/integrations/tailscale/setup-guide).

1. **Studio → Code Agents → Getting Started → *Tailscale Aperture* card → Generate API key.**
2. In Aperture settings, add the hook + a sync `pre_request` grant:
   ```json
   "hooks": {
     "highflame": {
       "url": "https://api.highflame.ai/v1/cerberus/agent/events",
       "apikey": "<HIGHFLAME_API_KEY>",
       "timeout": "30s",
       "fail_policy": "fail_open"
     }
   },
   "send_hooks": [
     { "name": "highflame", "events": ["pre_request"], "send": ["user_message", "request_body", "tools"] }
   ]
   ```
   Use `fail_closed` instead for guardrails where enforcement is mandatory (e.g. PII
   scrubbing for compliance) — per Aperture's guardrail failure-behavior guidance.
3. Author your Shield policies in Studio (each recipe has the exact click-path). The
   branded wording comes from the policy's `@reject_message`.

**The three Aperture actions** (a `pre_request` guardrail returns one):

| Action | Effect | Highflame use |
| --- | --- | --- |
| `allow` | request proceeds unchanged | nothing to act on |
| `block` | Aperture rejects; client sees status + message | secrets, SSN, injection — hard enforcement |
| `modify` | Aperture forwards a **replacement request body** | **scrub/redact PII**, strip tool declarations |

Guardrails **chain**: `modify` rewrites in place and the next guardrail sees the new body;
`block` terminates the chain.

**Why this route for a Tailscale shop.** No base-URL swap, no extra proxy — Aperture is
*already* in the path. Every decision carries `login_name` + `tailnet_name`: **per-developer
identity on every AI request**, visible in Studio → Code Agents. That's the story auth alone
can't tell.

> **Two real boundaries to know** (from Aperture's guardrail docs):
> - **Pre-request only.** Aperture guardrails inspect the *request* to the provider; there
>   are **no post-response guardrails** — filtering the model's *output* is a gateway
>   (Firehog) / native-hook capability, not Aperture.
> - **LLM boundary, not the tool boundary.** Guardrails fire on the LLM request (including
>   its `tools` array) but **not on the outbound MCP/tool call** the model later triggers.
>   To govern *tool execution*, use **MCP grants** or the **native IDE hook** (Overwatch),
>   not the Aperture guardrail.

---

## The scenario gallery

Each row is one recipe folder (Studio click-path **+** a runnable, CI-asserted Aperture
`pre_request` proof) and one planted vault file. Each sells a distinct piece of value.

### 1 · Data-loss prevention — *"our secrets & PII can't leave, even by accident"*

| # | Scenario | Aperture action | Status |
| --- | --- | --- | --- |
| 01 | [Block credential / secret leak](01-block-secrets/) | `block` + branded | ✅ ready |
| 02 | [Block PII — SSN / national ID](02-block-pii-ssn/) | `block` + branded | ✅ ready |
| 03 | [Redact / scrub PII — email, phone](03-pii-redaction/) | `modify` (transparent scrub) | ✅ ready (Cerberus `modify` shipped) |
| — | Source-code / IP egress · PHI (HIPAA) | `block` / `modify` | 📋 library |

### 2 · Prompt & agent attack defense — *"agents get attacked through their inputs"*

| # | Scenario | Aperture action | Status |
| --- | --- | --- | --- |
| 04 | [Indirect prompt injection](04-indirect-injection/) — poisoned tool output re-enters the next LLM request | `block` + branded | ✅ ready |
| — | Direct injection / jailbreak · multi-turn slow-burn | `block` | 📋 / 🔬 |

### 3 · Agentic action governance — *"agents *do* things — govern the actions"*

| # | Scenario | Surface | Status |
| --- | --- | --- | --- |
| 05 | [Govern dangerous tools / shell](05-tool-governance/) — resent tool calls blocked at the LLM boundary; `modify` strips tool declarations; execution-time = MCP grants / native hook | `block` + native | ✅ ready |
| — | Data-exfil kill-chain · runaway loop / budget | mixed | 📋 library |

### 4 · Supply-chain integrity (pre-runtime) — *"vet what you plug in"*

| # | Scenario | Surface | Status |
| --- | --- | --- | --- |
| 06 | [MCP server scan + SKILL scan](06-mcp-skill-scan/) | Overwatch / ramparts CLI | ✅ ready |

### 5 · Identity-scoped authz (Tailscale's wheelhouse) · 6 · Content safety · 7 · Proof

| # | Scenario | Surface | Status |
| --- | --- | --- | --- |
| — | Per-developer / per-node identity on every decision | attributed `allow`/`block` | 📋 library |
| — | Per-agent-source policy (`aperture_claude` vs `aperture_codex`) | scoped | 📋 library |
| — | Toxicity / phishing-URL / hallucination | `block` | 📋 library |
| — | Async `entire_request` observability (tool calls, cost, sessions) → Studio + Observatory | observe-only | 📋 library |

**Legend:** ✅ ready · 🚧 building (Tier-1) · 🛠️ needs a scoped platform change · 🔬 maturing ·
📋 library (one planted file + one folder).

---

## Where other integrations go

This `aperture/` folder is **one integration**. The cookbook holds others as siblings —
[`litellm/`](../litellm/) ships today; native IDE hooks (Overwatch), Firehog gateway,
Portkey, and MCP-gateway are their own folders. Pick the integration that matches how the
customer already runs their agents.

## Conventions

- **Env-only secrets**; each recipe ships `.env.example`. The key is the **Aperture service
  key** from Studio → Code Agents → Tailscale Aperture.
- **Prod by default** (`api.highflame.ai`).
- **Each recipe has a `smoke_test.py`** that POSTs a real Aperture `pre_request` payload to
  Cerberus and asserts the decision.
- **CI note:** [`smoke.yml`](../../.github/workflows/smoke.yml) discovers smoke tests at any
  depth (`find recipes -name smoke_test.py`), so nested recipes under `recipes/aperture/*/`
  run in CI (exit 2 = skip when keys/tools are absent).
