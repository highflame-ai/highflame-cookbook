# Highflame Cookbook

Runnable, copy-pasteable recipes for putting Highflame security in front of your AI
agents and LLM traffic — **without rewriting your stack.** Each recipe pairs a short
setup you do in [Highflame Studio](https://studio.highflame.ai) with a script you can run
to watch the guardrail work for yourself.

> **Looking for concepts, architecture, and product docs?** Those live at
> **[docs.highflame.ai](https://docs.highflame.ai)**. This repo is the hands-on,
> run-it-yourself companion.

---

## Start from where you are

There's no single "correct" way to adopt Highflame — the right path depends on how your
team already runs AI. Find your row:

| You run… | Recipe | What you change | What you gain |
| --- | --- | --- | --- |
| **The Highflame SDK directly** | [`recipes/sdk/`](recipes/sdk/) | `pip install highflame` + four lines | Full guardrail coverage on every prompt and tool call; the foundation all other recipes build on |
| **Coding agents** (Claude Code, Cursor, Codex…) behind **Tailscale Aperture** | [`recipes/aperture/`](recipes/aperture/) | Add one Highflame hook in Aperture | Block secret & PII leaks, redact PII, stop prompt injection — with per-developer identity on every request |
| **LiteLLM** already | [`recipes/litellm/`](recipes/litellm/) | Add Highflame as an upstream provider, or as a guardrail hook | Keep your routing and budgets; add the security + identity layer |
| **The OpenAI SDK / LangChain** from scratch | _coming soon_ | Point your base URL at Highflame | Policy enforcement + observability, zero instrumentation |
| **Your own agents / framework** | _coming soon_ | A guard call + a per-agent identity | Inline guardrails and per-agent identity |

Each row is one self-contained recipe directory — read only the one you need.

---

## What you'll need

Every recipe uses the same two things:

- **A Highflame account** — sign in at [studio.highflame.ai](https://studio.highflame.ai).
- **An API key** — generate one in Studio; each recipe's README says exactly where.

Recipes read the key from an environment variable and ship a `.env.example`. Never commit
a real key.

---

## Recipes

| Recipe | For | Format | Status |
| --- | --- | --- | --- |
| [**Highflame SDK**](recipes/sdk/) | Evaluate prompts & tools directly; the foundation | Marimo notebooks | ✅ ready |
| [**Code agents via Tailscale Aperture**](recipes/aperture/) | Securing Claude Code / Cursor / Codex behind Aperture | Python scripts | ✅ ready |
| [**LiteLLM**](recipes/litellm/) | Teams already running LiteLLM | Python scripts | ✅ ready |
| [**Overwatch policy catalog**](recipes/overwatch-policies/) | Securing IDE coding agents (Cursor, Claude Code, Copilot) — policy catalog + use-case packs | Reference doc | ✅ ready |
| OpenAI SDK / LangChain (greenfield) | New projects | — | coming soon |
| Portkey | Teams on Portkey | — | coming soon |

---

## How a recipe works

Every recipe follows the same shape, so a five-minute walkthrough looks the same each time:

1. **Set up once in Studio** — generate a key and turn on a policy (each recipe has the
   exact click-path, with screenshots).
2. **Run the proof** — a short script (or Marimo notebook) sends a representative request
   and shows you Highflame's decision: **allow**, **deny** (with the message you set in
   Studio), or **modify** (PII redacted).

### Scripts

```bash
cd recipes/<recipe>
cp .env.example .env          # add your Highflame API key
pip install -r requirements.txt
python <script named in the recipe README>
```

### Marimo notebooks (SDK recipes)

```bash
cd recipes/sdk
pip install -r requirements.txt
cp .env.example .env          # add your HIGHFLAME_API_KEY
marimo run 01_quickstart.py   # interactive browser UI
```

Or open any notebook in the full editor:

```bash
marimo edit 01_quickstart.py
```

---

## SDK recipe notebooks

The SDK recipe (`recipes/sdk/`) is a series of four interactive
[Marimo](https://marimo.io) notebooks — reactive Python cells you run and
modify in the browser.

| Notebook | What it covers |
| --- | --- |
| [`01_quickstart.py`](recipes/sdk/01_quickstart.py) | Connect, evaluate a prompt, `@shield.prompt` decorator |
| [`02_tool_security.py`](recipes/sdk/02_tool_security.py) | Guard tool calls, `@shield.tool`, rich ToolContext |
| [`03_agentic_sessions.py`](recipes/sdk/03_agentic_sessions.py) | Cross-turn session tracking, full OpenAI agent loop |
| [`04_wave_d_decisions.py`](recipes/sdk/04_wave_d_decisions.py) | All five AARM decisions: allow / deny / modify / step_up / defer |

---

Contributing to this repo? See [CONTRIBUTING.md](CONTRIBUTING.md).
