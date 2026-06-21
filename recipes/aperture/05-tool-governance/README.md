# 05 · Govern dangerous tools & shell

**The value:** *"Our agents run shell commands and call tools. A `curl | sh` from a sketchy
source, or an agent reaching for a destructive command, should be stopped — and we want to
know which tools our agents even use."*

Coding agents resend their conversation — including prior tool calls — on each turn.
Highflame evaluates those tool calls before the model's next step, so a dangerous command in
the agent's history is caught and blocked.

**Try it in the demo app:** ask the agent to *"run the project's setup script
([`scripts/setup.sh`](https://github.com/highflame-ai/highflame-demo-app/blob/main/scripts/setup.sh))"* —
the `curl … | sh` is blocked.

> **Where governance lives.** The guardrail acts at the model-request boundary: it blocks a
> dangerous command *in the request* and can strip risky tool declarations before the model
> sees them. To gate the actual tool *execution*, pair this with MCP grants (limit which
> tools are exposed) or Highflame's native IDE integration.

---

## Set up the policy in Studio

1. **Studio → Code Agents → Tailscale Aperture** (one-time hook setup — see [the track setup](../README.md#one-time-setup)).
2. **Policies → New Policy → Guardrail.** Trigger on **shell-command risk** — block when a
   command both reaches the network and executes code (the `curl | sh` shape), or on a high
   tool-risk score; action **block**; mode **enforce**; custom message — *"Highflame
   Security has detected unauthorized shell access."*
   ![Shell governance policy](img/01-trigger-shell.png)
3. Save & activate.

---

## See the decision

```bash
cp .env.example .env        # set HIGHFLAME_API_KEY (the Aperture service key)
pip install -r requirements.txt
python aperture_event.py
```

```text
{
  "action": "block",
  "status_code": 403,
  "message": "Highflame Security has detected unauthorized shell access."
}
```

## Verify

```bash
python smoke_test.py
```

Confirms the dangerous tool call is blocked.

---

## Notes

- Applies to agents that resend tool history in their requests (Codex and others). To govern
  live tool execution for any agent, use MCP grants or Highflame's native IDE integration.
- **Two surfaces, both covered.** The structured tool-call above is how Codex/OpenAI agents
  carry a command. When a dangerous command instead rides in a Claude/Anthropic *prompt*
  ("run `curl … | sh`"), Highflame still blocks it — semantic threat detection catches the
  intent — so Claude Code users are protected even without a tool-call surface.
- **Discovery is half the value:** even in monitor mode, every tool call flows into Studio →
  Code Agents, giving you an inventory of which tools and commands your agents actually run
  before you write a single blocking policy.
- The command targets `evil.example`, reserved and non-routable.
