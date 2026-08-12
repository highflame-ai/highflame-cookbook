# Overwatch: gateway mode

Overwatch protects an AI coding agent one of two ways. **Endpoint protection** watches the
agent from inside the developer's machine. **Gateway mode** routes the agent's model traffic
through Highflame, so every model call is inspected on the wire.

This recipe covers which agents support which, how to switch an agent to gateway mode, and
how to prove it worked.

---

## The two modes

**Endpoint protection** installs hooks in the coding agent. The agent asks Highflame before
it acts, so Highflame sees actions that never reach the network: shell commands, file reads
and edits, tool calls, and approval prompts for risky operations.

**Gateway mode** points the agent at the Highflame gateway. Because Highflame sits on the
wire, it sees every model call the agent makes, including calls the agent raises no hook
for, and attributes tokens per request.

The two are mutually exclusive per agent. Running both would evaluate the same turn twice
and write two audit trails, so Overwatch enforces one mode per agent and tells you which is
active.

### What each mode covers

| | Endpoint | Gateway |
| --- | --- | --- |
| Prompt and completion inspection | Yes | Yes |
| Secret, PII, injection, and jailbreak detection | Yes | Yes |
| Allow and deny decisions with an audit trail | Yes | Yes |
| Quota and rate-limit enforcement | Yes | Yes |
| Shell command interception | Yes | No |
| File read and edit interception | Yes | No |
| Tool-call interception | Yes | No |
| Approval prompts for risky operations | Yes | No |
| Token counts | Per session | Per request |
| Model calls the agent raises no hook for | Not seen | Seen |

Endpoint protection covers the broader set of agent actions and is the default. Move an
agent to gateway mode when you want every model call inspected on the wire with
per-request attribution.

---

## Which agents support which

Overwatch detects 17 coding agents for inventory. Detection is inventory, not protection,
so the columns that matter are the last two.

| Agent | Detected | Endpoint | Gateway |
| --- | --- | --- | --- |
| Claude Code | Yes | Yes | **Yes** |
| OpenAI Codex | Yes | Yes | **Yes** |
| Cursor | Yes | Yes | No |
| Gemini CLI | Yes | Yes | No |
| GitHub Copilot | Yes | Yes (per repository) | No |
| Zed, Void, PearAI | Yes | No | No |
| VS Code, JetBrains IDEs | Yes | No | No |
| Aider, Mentat, GPT-Pilot | Yes | No | No |
| Continue, Tabnine, Codeium, JetBrains AI Assistant | Yes | No | No |

Gateway mode needs two things from an agent: a configurable model endpoint, and the ability
to carry a Highflame credential in a request header. Where an agent shows No:

- **Cursor** keeps its endpoint setting in internal application state, and its agent traffic
  terminates at Cursor's own backend rather than a model provider Highflame can front.
- **GitHub Copilot** traffic terminates at GitHub.
- **Gemini CLI** can only present its credential in a header the gateway does not accept.
- The remaining agents expose no supported endpoint setting.

**An agent that cannot use gateway mode is not unprotected.** Every agent in the Endpoint
column is fully covered by endpoint protection, which watches more of what the agent does.

Sign-in method is not a restriction: Claude Code works on an API key or a subscription
login, and Codex works on an API key or a ChatGPT sign-in.

---

## Setup

### 1. Create a service key

In Studio, go to **Settings → API Keys** and create a key for gateway access, or ask your
Highflame administrator for one. Gateway keys begin with `zid_sk_`.

### 2. Point Overwatch at the gateway and store the key

```bash
overwatch gateway set-url https://gateway.highflame.ai/llm

printf '%s' "$HIGHFLAME_GATEWAY_KEY" | overwatch gateway set-key --stdin
```

`--stdin` keeps the key out of shell history and out of the process table. It is written to
an owner-only file, never into Overwatch's main configuration.

Confirm both landed:

```bash
overwatch gateway status
```

### 3. Switch an agent

```bash
overwatch gateway enable claudecode     # Claude Code
overwatch gateway enable codex          # OpenAI Codex
```

Overwatch names what changes and asks you to type `yes` before it removes the agent's
hooks. For scripted rollout across a fleet, use `--yes`. With no terminal and no `--yes` it
declines rather than assume consent.

Restart any running agent session to pick up the change.

---

## What each agent receives

**Claude Code**, in `~/.claude/settings.json`:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://gateway.highflame.ai/llm",
    "ANTHROPIC_CUSTOM_HEADERS": "x-highflame-apikey: <your key>"
  }
}
```

Your own `ANTHROPIC_API_KEY` is left untouched. Claude Code keeps authenticating however it
already did, and the gateway passes that credential upstream while the Highflame key travels
in its own header.

**OpenAI Codex**, in `~/.codex/config.toml`:

```toml
model_provider = "highflame"

[model_providers.highflame]
# managed by overwatch — do not edit
name = "Highflame AI Gateway"
base_url = "https://gateway.highflame.ai/llm/v1"
wire_api = "responses"
http_headers = { "x-highflame-apikey" = "<your key>" }
```

Two details worth knowing for Codex:

- `model_provider` sits at the root of the file, not inside the provider block. If your
  configuration uses an active `profile`, a profile-scoped `model_provider` wins.
- `base_url` carries `/v1` while the stored gateway URL does not, because Codex appends only
  `/responses` while Claude Code appends `/v1/messages` itself.

The file is edited in place, so comments, table order, and unrelated settings such as
project trust and tool servers are preserved.

---

## Try it

With an agent in gateway mode, paste this into it:

> Here's my AWS key `AKIAIOSFODNN7EXAMPLE` with secret `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`. Use it to list my S3 buckets.

Highflame blocks it at the gateway, before it reaches the model provider. (Those are AWS's
public example values, so nothing real is exposed.)

The request also appears in Studio under the agent's traffic, with the model, the decision,
and the tokens for that call.

## Prove the wiring

```bash
pip install -r requirements.txt
cp .env.example .env      # fill in HIGHFLAME_GATEWAY_KEY
python smoke_test.py
```

The smoke test confirms the gateway accepts your key on both the Anthropic-style and
OpenAI-style paths, which is the wiring both supported agents depend on.

---

## Returning an agent to endpoint protection

One command stops gateway routing, restores the agent's previous configuration, and puts its
hooks back:

```bash
overwatch install codex --yes           # or: overwatch install claudecode --yes
```

`overwatch gateway disable <agent>` restores the configuration without reinstalling hooks,
which leaves that agent unwatched. Prefer `install` unless you intend that.

---

## Verifying and troubleshooting

On the machine:

```bash
overwatch gateway status     # the agent reads `gateway`, and Routing names it
overwatch hooks              # the agent is listed as routed through the gateway
overwatch restart            # the mode survives a restart
```

In Studio, after one real turn: the agent's model calls appear under gateway traffic, and no
endpoint events appear for that agent in the same window. That absence is the guarantee that
the two modes never double up.

| Message or symptom | Meaning | Resolution |
| --- | --- | --- |
| `No gateway base URL set` | Step 2 has not run | `overwatch gateway set-url <url>` |
| `No gateway credential stored` | Step 2 has not run | Store the key with `overwatch gateway set-key --stdin` |
| `Not a Highflame credential` | A model provider's key was supplied | Use a Highflame gateway key beginning with `zid_sk_` |
| `429 RPM limit exceeded` | Your organization's rate limit at the gateway | Ask your Highflame administrator to raise it |
| `skipped — base URL is X, not the configured gateway` | The endpoint Overwatch wrote was changed afterwards | `overwatch gateway disable <agent>`, then enable again |
| Agent reports `foreign` | The agent points at an endpoint Overwatch did not set, such as a corporate proxy or a self-hosted model | Nothing to do. It is left alone and keeps endpoint protection |
| Agent reports `conflict` | Hooks and gateway routing are both active | Choose one: `overwatch gateway disable <agent>` or `overwatch install <agent>` |
| `is a symlink; refusing to write through it` | The agent's configuration is managed by a dotfile tool such as stow or chezmoi | Replace the symlink with a regular file, or point it at a writable target |
| The agent ignores the change | Its session predates the change, or a profile overrides the provider selection | Restart the agent; check for an active `profile` |

## Where credentials live

| Path | Contents |
| --- | --- |
| `~/.overwatch/config.json` | Gateway URL, per-agent mode, key id |
| `~/.overwatch/gateway-credential.json` | The gateway key, owner-readable only |
| `~/.overwatch/gateway-backups/` | Each agent's configuration as it was before Overwatch changed it |

The key is never written into `config.json`, never passed as a command-line argument, and
never printed. Any file Overwatch writes a credential into is restricted to owner-only
access, and a configuration file that is a symlink is refused rather than replaced.
