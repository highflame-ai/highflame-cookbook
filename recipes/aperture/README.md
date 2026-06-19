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
the policy in Studio.

**Identity on every request — the Tailscale-native advantage.** Every decision carries the
developer's login and tailnet, so a block is attributed to a real person on a real device,
visible in Studio → Code Agents. That's the per-developer accountability authentication
alone can't give you.

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
  tailnet.

## Other integrations

This `aperture/` folder is one integration. The cookbook also has [`litellm/`](../litellm/),
with more on the way — pick the one that matches how your team already runs agents.
