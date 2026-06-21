# Highflame + Tailscale Aperture

Your developers run coding agents — **Claude Code**, Cursor, Codex, Gemini CLI — inside
your tailnet, behind **[Tailscale Aperture](https://tailscale.com/docs/aperture)**, the AI
gateway that routes their LLM traffic with Tailscale identity attached. **Highflame plugs
into Aperture as a guardrail:** every prompt and tool call is checked *before* it reaches
the model provider, with the developer's identity on it. When a policy fires, the developer
sees a clear **Highflame Security** message — the one you wrote in Studio, not a generic error.

One setup secures every Aperture-routed agent — Claude Code, Codex, Cline, Gemini CLI,
Roo Code.

```
Coding agent ──▶ Tailscale Aperture ──guardrail──▶ Highflame ──▶ allow · block · redact
                       │                                          (+ the message you set)
                       └──◀──── "Highflame Security has blocked…" ◀───┘
```

> **Try it end to end.** Open the companion app —
> [`highflame-demo-app`](https://github.com/highflame-ai/highflame-demo-app), a small
> "Acme CRM" service with realistic (planted, fake) secrets and PII — in your agent and
> watch Highflame catch each issue in the natural flow of work.

---

## Set it up

→ Follow the **[live-demo runbook](live-demo.md)** for the complete step-by-step: enable
Aperture, point Claude Code at it, generate your Highflame key and add the guardrail hook,
and turn on the Studio policies. Reference:
[docs.highflame.ai/integrations/tailscale](https://docs.highflame.ai/integrations/tailscale/setup-guide).

---

## How it works

**You control the message.** What a developer sees on a block is the message you write on
the policy in Studio. Highflame frames it as **"Highflame Security has blocked your prompt
because …"** automatically, so you can write just the reason (e.g. *"it contained a national
ID"*); if your message already starts with "Highflame Security", it's shown verbatim, never
double-prefixed.

**Identity on every request — the Tailscale-native advantage.** Every decision carries the
developer's login and tailnet, so a block is attributed to a real person on a real device,
visible in Studio → Code Agents. That's the per-developer accountability authentication
alone can't give you. How that login becomes a Highflame user is explained in
[**Identity & access**](#identity--access) below.

### What the guardrail does

A Highflame check returns one of three outcomes, which Aperture applies:

| Outcome | What happens |
| --- | --- |
| **Allow** | the request continues unchanged |
| **Block** | the request is rejected with the message you set in Studio; it never reaches the model |
| **Redact** | Highflame returns a scrubbed request (e.g. PII masked) and Aperture forwards that instead |

### What it sees — and where to govern the rest

The Aperture guardrail runs at the **model-request** boundary: it inspects the prompt and
the tools a request declares, just before the provider call. Two complementary surfaces
cover the rest:

- **Model output** (the provider's response) is governed on Highflame's gateway and
  native IDE-hook integrations.
- **Live tool execution** (the actual shell or MCP call an agent runs) is governed with
  MCP grants or Highflame's native IDE integration. The pre-request guardrail still catches
  a dangerous command *in the request* and can strip risky tool declarations before the
  model sees them.

---

## Identity & access

Aperture runs inside your tailnet, so it already knows *who* sent each request: Tailscale
verifies every developer through your identity provider and attaches their email — the
`login_name` — to the request. Highflame turns that into a real, governed identity:

1. **Match the email to a Highflame user.** Highflame looks up the `login_name` against the
   members of your Highflame organization.
2. **Check membership (deny-by-default).** If the email belongs to a member, the request
   proceeds and the event is attributed to that person — plus a per-developer agent identity,
   so each developer's coding agent has its own traceable identity. **If the email is not a
   member of your organization, the request is denied** — people outside your org can't route
   traffic through your gateway, even on your tailnet.
3. **Attribute everything.** From there, every decision (allow / block / redact) is recorded
   against the real developer in **Studio → Code Agents** — no shared service account, no
   anonymous traffic.

> ### ⚠️ One requirement: same email on both sides
>
> Highflame matches a developer by **email**. A developer must sign in to Highflame with the
> **same email address** they use for Tailscale / Aperture. If `alice@yourco.com` is her
> Tailscale login, she must be a member of your Highflame organization as `alice@yourco.com`
> — otherwise Highflame can't recognize her and her requests are denied.
>
> Practically: when you invite your developers to Highflame (Studio → members), use the same
> email addresses they already use in Tailscale.

No member matches a login? That request is blocked at the identity layer **before** any
content policy runs — so a deny you didn't expect is usually a *membership* problem (wrong or
un-invited email), not a content one. See [troubleshooting](live-demo.md#if-something-doesnt-fire).

---

## The scenarios

Run these in the [live demo](live-demo.md): open the
[demo app](https://github.com/highflame-ai/highflame-demo-app) in your agent and try the
matching prompt. Each links to a recipe with the exact Studio policy behind it.

**Data-loss prevention** — *"our secrets and PII can't leave, even by accident"*
- [**01 · Block a credential / secret leak**](01-block-secrets/) — a pasted or hardcoded API key is blocked.
- [**02 · Block PII (SSN / national ID)**](02-block-pii-ssn/) — national IDs never reach the provider.
- [**03 · Redact PII (email, phone)**](03-pii-redaction/) — the address is scrubbed; the developer stays productive.

**Prompt & agent attack defense** — *"agents get attacked through their inputs"*
- [**04 · Block indirect prompt injection**](04-indirect-injection/) — a hidden instruction in a doc or tool result is caught.

**Agentic action governance** — *"agents *do* things — govern the actions"*
- [**05 · Govern dangerous tools & shell**](05-tool-governance/) — a `curl … | sh` in an agent's tool history is blocked.

**Supply-chain integrity** — *"vet what you plug in"*
- [**06 · MCP server scan + SKILL scan**](06-mcp-skill-scan/) — scan MCP servers and agent skills for poisoning before they're used.

Each scenario maps to a planted issue in the demo app. Want a scenario that isn't here —
toxicity, phishing-URL detection, hallucination, per-agent identity policy? They're all
supported; ask your Highflame contact and we'll add the recipe.

---

## Good to know

- **The key** is the Aperture service key from Studio → Code Agents → Tailscale Aperture.
- **Monitor first, then enforce.** A policy in monitor mode records what it *would* have
  done while still letting traffic through; switch it to enforce when you're ready — no
  Aperture change needed.
- **Run it yourself.** Each recipe ships a short script that sends a representative request
  to Highflame and prints the decision, so you can confirm the setup without standing up a
  tailnet. If your org enforces the identity gate, set `HIGHFLAME_APERTURE_LOGIN` to your
  Highflame login email first (see [Identity & access](#identity--access)), so the script
  runs as a real member instead of the placeholder `developer@example.com`.

## Other integrations

This `aperture/` folder is one integration. The cookbook also has [`litellm/`](../litellm/),
with more on the way — pick the one that matches how your team already runs agents.
