# Highflame Cookbook

Runnable, copy-pasteable recipes for putting Highflame security in front of your AI
agents and LLM traffic — **without rewriting your stack.** Each recipe pairs a short
setup you do in [Highflame Studio](https://studio.highflame.ai) with a script you can run
to watch the guardrail work for yourself.

> **Looking for concepts, architecture, and product docs?** Those live at
> **[docs.highflame.ai](https://docs.highflame.ai)**. This repo is the hands-on,
> run-it-yourself companion. Registry connector setup for Entra, Okta, Google
> Workspace, Google Agent Engine, and AWS Bedrock lives in
> [`recipes/connectors/`](recipes/connectors/). Browser Security install-and-connect
> for Chrome, Firefox, and Safari lives in
> [`recipes/browser-protection/`](recipes/browser-protection/). Overwatch
> install-and-connect (one npm install, every coding agent on the machine) lives in
> [`recipes/agent-protection/`](recipes/agent-protection/).

---

## Start from where you are

There's no single "correct" way to adopt Highflame — the right path depends on how your
team already runs AI. Find your row:

| You run… | Recipe | What you change | What you gain |
| --- | --- | --- | --- |
| **The Highflame SDK directly** | [`recipes/sdk/`](recipes/sdk/) | `pip install highflame` + four lines | Full guardrail coverage on every prompt and tool call; the foundation all other recipes build on |
| **Coding agents** (Claude Code, Cursor, Codex…) behind **Tailscale Aperture** | [`recipes/aperture/`](recipes/aperture/) | Add one Highflame hook in Aperture | Block secret & PII leaks, redact PII, stop prompt injection — with per-developer identity on every request |
| **Claude Code, Codex CLI, or GitHub Copilot** and want them to talk to Highflame directly | [`recipes/ai-gateway/`](recipes/ai-gateway/) | Point the agent's base URL at the Highflame AI Gateway | Every model call goes through Highflame — logging, policy, and routing — without changing how you use the CLI |
| **LiteLLM** already | [`recipes/litellm/`](recipes/litellm/) | Add Highflame as an upstream provider, or as a guardrail hook | Keep your routing and budgets; add the security + identity layer |
| **AI agents from an IdP** (Google Workspace, Okta, Entra…) | [`recipes/agent-governance/`](recipes/agent-governance/) | Connect your IdP; adopt agents; attach a guardrail | Discover every agent, give each an accountable owner, and govern what it does at runtime |
| **Registry connectors** (Entra, Okta, Google Workspace, Agent Engine, AWS Bedrock) | [`recipes/connectors/`](recipes/connectors/) | Configure the provider-side app / IAM / token Highflame needs | Wire Studio discovery so agents show up ready to adopt |
| **Browser AI chat** (ChatGPT, Claude, Gemini…) | [`recipes/browser-protection/`](recipes/browser-protection/) | Install Highflame Browser Security in Chrome, Firefox, or Safari and connect it to Studio | Prompts, pastes, and uploads are checked before they leave the browser |
| **IDE coding agents** (Cursor, Claude Code, Copilot…) | [`recipes/agent-protection/`](recipes/agent-protection/) | `npm install -g @highflame/overwatch` once | Every coding agent on the machine is monitored |
| **Highflame already, and you want the data out** | [`recipes/usage-reporting/`](recipes/usage-reporting/) | Nothing — one API key | Pull every event, what it cost, and what it shipped, as JSON or CSV for your BI tool or an LLM |
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
| [**AI Gateway**](recipes/ai-gateway/) | Point Claude Code, Codex, or GitHub Copilot at the Highflame AI Gateway | Reference docs | ✅ ready |
| [**LiteLLM**](recipes/litellm/) | Teams already running LiteLLM | Python scripts | ✅ ready |
| [**Overwatch policy catalog**](recipes/overwatch-policies/) | What Overwatch catches for IDE coding agents (Cursor, Claude Code, Copilot) | Reference doc | ✅ ready |
| [**Agent governance**](recipes/agent-governance/) | Discovering, adopting & guarding agents from Google Workspace / Okta / Entra | Python script | ✅ ready |
| [**Registry connectors**](recipes/connectors/) | Provider setup for Entra, Okta, Google Workspace, Google Agent Engine, AWS Bedrock | Reference docs | ✅ ready |
| [**Browser protection**](recipes/browser-protection/) | Connect Highflame Browser Security in Chrome, Firefox, or Safari | Reference docs | ✅ ready |
| [**Agent protection**](recipes/agent-protection/) | Connect Overwatch (`@highflame/overwatch` on npm); one install monitors every coding agent | Reference docs | ✅ ready |
| [**Usage, cost & productivity reporting**](recipes/usage-reporting/) | Pulling your events, spend and productivity metrics out programmatically | Python scripts | ✅ ready |
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
