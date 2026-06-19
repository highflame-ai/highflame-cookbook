# Highflame Cookbook

Runnable, copy-pasteable recipes for putting the Highflame platform in front of your
LLM and MCP traffic — **without rewriting your stack.**

Every recipe in here is a real script or notebook that runs against **prod / SaaS**
(`*.highflame.ai`), not pseudo-code. The CI in this repo runs the smoke tests on a
schedule against a canary tenant, so when the platform changes, a broken recipe turns
the build red instead of silently rotting in a doc.

> **Where this fits.** This repo is the *runnable territory*. The narrative,
> concepts, and decision trees live on **[docs.highflame.ai](https://docs.highflame.ai)**
> and link back into these recipes. SDK-native quickstarts (CrewAI, LangGraph, Strands,
> ZeroID) live next to the SDK in
> [`highflame-sdk/examples`](https://github.com/highflame-ai/highflame-sdk/tree/main/python/examples).
> Rule of thumb: **if the recipe's whole point requires `import highflame`, it belongs in
> the SDK examples; if it's about the platform (gateway, policies, third-party tools), it
> belongs here.**

---

## Start from where you are

There is no single "correct" way to adopt Highflame. The right path depends on what you
already run. Find your row:

| You are… | Path | What you change | What Highflame adds |
| --- | --- | --- | --- |
| **Greenfield** — wiring up the OpenAI SDK / LangChain / LlamaIndex from scratch | **Gateway base-URL swap** (Firehog) | One line: `base_url` → `gateway.highflame.ai` + an API-key header | Policies + observability + identity, zero instrumentation |
| **Building on your own framework / custom agents** | **SDK inline** (`@shield` / `.guard()`) **+ ZeroID** | A decorator or a guard call; mint a per-agent identity | Inline guardrails **and per-agent identity** — the "auth isn't enough" story |
| **Already running LiteLLM / Portkey / CF AI Gateway** | **Compose, don't replace** → [`recipes/litellm/`](recipes/litellm/) | Add Highflame as an upstream provider, **or** a guardrail hook | Keep your routing/budgets; add the security + identity layer |
| **Want the least-invasive thing possible** | **Pure proxy** (Firehog via an env var) | An env var | Traffic visibility + policy enforcement |
| **Securing MCP / tool traffic** | **MCP gateway** (Firehog `/mcp/{scope}/{slug}`, OAuth 2.1) | Point your MCP client at Firehog | Tool-call policy + downstream token brokering |

Each row is one recipe directory. They are independent — read only the one you need.

---

## The two services you'll touch

| Service | Prod / SaaS URL | Role | Auth it accepts |
| --- | --- | --- | --- |
| **Firehog** (gateway) | `https://gateway.highflame.ai` | OpenAI-compatible reverse proxy. Routes by `{provider}/{model}`, applies Shield inline, emits traces. | `X-Highflame-APIKey: <key>` or `Authorization: Bearer hf_sk_*`; the upstream provider key rides along in `Authorization`. |
| **Shield** (guardrails) | `https://api.highflame.ai/v1/shield` | Detection + Cedar policy engine. `POST /v1/shield/guard` returns a decision. | **JWT only** (ES256/RS256) or internal service secret — *not* a raw API key. The SDK mints the JWT for you. |

> Most recipes only need Firehog. You only call Shield directly when you want a policy
> check *without* routing provider traffic through the gateway — see Mode B in the
> LiteLLM recipe.

---

## Recipes

| Recipe | For | Status |
| --- | --- | --- |
| [`recipes/litellm/`](recipes/litellm/) | Teams already on LiteLLM | ✅ ready |
| `recipes/greenfield-openai-sdk/` | New projects on the OpenAI SDK / LangChain | 🚧 planned |
| `recipes/portkey/` | Teams already on Portkey | 🚧 planned |
| `recipes/mcp-gateway/` | Securing MCP/tool traffic | 🚧 planned |
| `recipes/sdk-identity/` | Per-agent identity with ZeroID | 🚧 planned (or link to SDK examples) |

---

## Conventions

- **Secrets via env only.** Every recipe reads from environment variables and ships a
  `.env.example`. Never commit a real key.
- **Prod by default.** Defaults point at `*.highflame.ai`. Override with the documented
  env vars to target dev1 (`*-dev.highflame.dev`) if you have access.
- **Each recipe has a `smoke_test.py`.** It's the CI entrypoint and doubles as the
  fastest way to confirm your keys work end-to-end.
- **CI runs the smoke tests.** [`.github/workflows/smoke.yml`](.github/workflows/smoke.yml)
  runs every recipe's `smoke_test.py` on change and nightly. Set `HIGHFLAME_API_KEY` (and
  the provider keys) as repo secrets to make the scheduled run exercise the canary tenant;
  without them the scripts exit early and the build stays green.
