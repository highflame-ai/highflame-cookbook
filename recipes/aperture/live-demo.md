# Live demo runbook — secure Claude Code with Highflame + Tailscale Aperture

One-time setup, then a ~3-minute walkthrough you can run live or screen-record. Everything
runs through **real Tailscale Aperture** — the product you're selling — with Highflame
catching issues in the natural flow of a developer's work.

## The story you're telling

A developer uses Claude Code on a normal app. They aren't trying to do anything wrong — but
the code has a hardcoded AWS key, the customer data has SSNs, an onboarding doc was copied
from an untrusted source. As they ask Claude for routine help, **Aperture routes every
request and Highflame catches each issue before it reaches the model** — with a clear
"Highflame Security…" message in Claude Code, and every event attributed to the developer in
Highflame Studio.

---

## Part 1 · One-time setup (~15 minutes)

You need: a Tailscale tailnet, an Anthropic API key (the provider Aperture forwards to), a
Highflame account, and Claude Code installed.

### 1. Turn on Aperture and add Anthropic

If Aperture isn't running in your tailnet yet, follow Tailscale's
**[Get started with Aperture](https://tailscale.com/docs/aperture/get-started)** guide — sign
up at [aperture.tailscale.com](https://aperture.tailscale.com), then add Anthropic as a
provider ([Set up Anthropic](https://tailscale.com/docs/aperture/how-to/use-anthropic)).
In **Administration → Configuration**, the provider block looks like:

```json
{
  "providers": {
    "anthropic": {
      "baseurl": "https://api.anthropic.com",
      "apikey": "<your-anthropic-api-key>",
      "models": ["claude-sonnet-4-6", "claude-opus-4-8"],
      "authorization": "x-api-key",
      "compatibility": { "anthropic_messages": true }
    }
  }
}
```

> Include the model your Claude Code actually uses in `models`, or Aperture may reject the request.

Aperture now listens in your tailnet at `http://<aperture-hostname>` (dashboard at
`http://<aperture-hostname>/ui/`). Confirm it routes:

```bash
curl -s http://<aperture-hostname>/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-haiku-4-5-20251001","max_tokens":25,"messages":[{"role":"user","content":"respond with: hello"}]}'
```

### 2. Generate a Highflame API key

In **[Highflame Studio](https://studio.highflame.ai/) → Code Agents → Getting Started → the
*Tailscale Aperture* card → Generate API key.** Copy it.

### 3. Add the Highflame guardrail hook in Aperture

In **Administration → Configuration**, define the Highflame hook and attach a synchronous
`pre_request` check to the grant that carries your demo traffic
([Tailscale: Set up a guardrail](https://tailscale.com/docs/aperture/how-to/set-up-guardrails)):

```json
"hooks": {
  "highflame": {
    "url": "https://api.highflame.ai/v1/cerberus/agent/events",
    "apikey": "<HIGHFLAME_API_KEY>",
    "timeout": "30s",
    "fail_policy": "fail_open"
  }
}
```

…and inside the grant:

```json
"send_hooks": [
  { "name": "highflame", "events": ["pre_request"], "send": ["user_message", "request_body", "tools"] }
]
```

Use `fail_closed` for compliance-critical guardrails (e.g. PII scrubbing).

### 4. Turn on the demo policies in Highflame Studio

In **Studio → Code Agents → Policies**, enable:

- the **baseline permit** policy — so normal requests are allowed (without it, *everything*
  is denied), and
- the scenario guardrails you want to show. Each scenario recipe has the exact click-path:
  [01 secrets](01-block-secrets/) · [02 SSN](02-block-pii-ssn/) · [03 email redaction](03-pii-redaction/) ·
  [04 injection](04-indirect-injection/) · [05 shell](05-tool-governance/).

Set them to **enforce** for the demo (monitor only records — it won't block).

### 5. Point Claude Code at Aperture

Edit `~/.claude/settings.json`
([Tailscale: Use Claude Code with Aperture](https://tailscale.com/docs/aperture/how-to/use-claude-code)):

```json
{
  "apiKeyHelper": "echo '-'",
  "env": {
    "ANTHROPIC_BASE_URL": "http://<aperture-hostname>"
  }
}
```

No Anthropic key is needed on the client — Aperture supplies it. Use `http://`; the tailnet
encrypts with WireGuard.

### 6. Get the demo app

```bash
git clone https://github.com/highflame-ai/highflame-demo-app
cd highflame-demo-app && npm install
claude
```

You're set: **Claude Code → Aperture → Highflame**, on a realistic app with planted issues.

---

## Part 2 · The walkthrough (~3 minutes)

Run these in order in Claude Code, inside the demo app. Each is a normal developer request;
Highflame catches the issue and Claude Code shows the message.

| # | Type this in Claude Code | What the prospect sees |
| --- | --- | --- |
| 1 | *"Why is the S3 upload failing? Check `src/config.js`."* | **Blocked** — "Highflame Security has blocked your prompt because it violated Enterprise Policy." The hardcoded AWS key never reaches the model. |
| 2 | *"Summarize the customers in `data/customers.csv`."* | **Blocked** — national ID (SSN) detected. |
| 3 | *"Draft a follow-up email to the first lead in `data/customers.csv`."* | **Redacted** — Claude writes the email to `[REDACTED]`; the address never left your network. |
| 4 | *"Follow the setup steps in `docs/integrations.md`."* | **Blocked** — a hidden instruction in the doc is caught (indirect prompt injection). |
| 5 | *"Run the project's setup script."* | **Blocked** — unauthorized shell (`curl … \| sh`). |

Then **flip to Highflame Studio → Code Agents**: every one of those is recorded, attributed
to *you* (your tailnet login), with the policy that fired.

---

## If something doesn't fire

- **Everything is blocked, even "hello"** → the baseline permit policy isn't enabled (Step
  4). Enable it.
- **Nothing is blocked** → the policy is in monitor mode (switch to enforce), or Claude Code
  isn't actually routing through Aperture (re-run the Step 1 `curl`, and confirm
  `ANTHROPIC_BASE_URL`).
- **The email isn't redacted (scenario 3)** → confirm the email policy's action is set to
  *redact / mask* (not block).
- **No events in Studio** → check the hook `apikey` and that `send_hooks` is on the grant
  your traffic matches.
- More: [Highflame × Tailscale troubleshooting](https://docs.highflame.ai/integrations/tailscale/troubleshooting).

