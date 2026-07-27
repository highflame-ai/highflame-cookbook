# 05 · Govern dangerous tools & shell

**The value:** _"Our agents run shell commands and call tools. A `curl | sh` from a sketchy
source, or an agent reaching for a destructive command, should be stopped — and we want to
know which tools our agents even use."_

Coding agents resend their conversation — including prior tool calls — on each turn.
Highflame evaluates those tool calls before the model's next step, so a dangerous command in
the agent's history is caught and blocked.

**Try it in the demo app:** ask the agent to _"run the project's setup script
([`scripts/setup.sh`](https://github.com/highflame-ai/highflame-demo-app/blob/main/scripts/setup.sh))"_ —
the `curl … | sh` is blocked.

> **Where governance lives.** The guardrail acts at the model-request boundary: it blocks a
> dangerous command _in the request_ and can strip risky tool declarations before the model
> sees them. To gate the actual tool _execution_, pair this with MCP grants (limit which
> tools are exposed) or Highflame's native IDE integration.

---

## Set up the policy in Studio

1. **Studio → Code Agents → Tailscale Aperture** (one-time hook setup — see [the track setup](../README.md#one-time-setup)).
2. **Deploy the template (recommended).** Open the **Studio → Code Agents → Policies** tab
   and click the **Tool Permissioning** category — **Shell & Command Governance**
   (`tools.shell-command-governance`) appears under **Available Templates**. Deploy it (it's
   a **Code Agents** template), set mode **enforce**, and, optionally, a custom message —
   _"Highflame Security has detected unauthorized shell access."_ The template ships the
   exact rules in step 3, so you don't have to build them.
3. **Or build it from scratch.** In **Studio → Code Agents → Policies**, under the **Tool
   Permissioning** category, create a **New Policy** on action **`call_tool`**,
   action **block**, mode **enforce**. Add these conditions — each is its own rule, and
   Highflame ORs separate rules, so a request is blocked if _any_ matches:
   - **Download-and-run** (`curl … | sh`): `tool_operation_classes` **contains**
     `network_access` **AND** `tool_operation_classes` **contains** `execute_enabling`.
   - **High tool-risk:** `tool_risk_score` **≥** `86`, **or** `tool_category` **is**
     `dangerous`.

   The `tools.shell-command-governance` template also blocks _sensitive tools at elevated
   risk_ (`tool_is_sensitive` **and** `tool_risk_score` ≥ `71`) and _exfiltration /
   destructive action sequences_ (`suspicious_pattern`) — deploy it to get all four rules.

4. Save & activate.

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
  carry a command. When a dangerous command instead rides in a Claude/Anthropic _prompt_
  ("run `curl … | sh`"), Highflame still blocks it — semantic threat detection catches the
  intent — so Claude Code users are protected even without a tool-call surface.
- **Discovery is half the value:** even in monitor mode, every tool call flows into Studio →
  Code Agents, giving you an inventory of which tools and commands your agents actually run
  before you write a single blocking policy.
- The command targets `evil.example`, reserved and non-routable.

---

## Troubleshooting

- **`502 "API key resolution failed"`** — the key isn't known to the environment you're
  calling. Almost always a wrong or stale key: re-copy the credential from the same Studio
  environment the endpoint belongs to, and `unset HIGHFLAME_API_KEY` in your shell first — an
  exported variable silently overrides `.env`.
- **`403 "…identity is not a member of this Highflame organization"`** — the key resolved,
  but `HIGHFLAME_APERTURE_LOGIN` isn't recognized as a member of the org/project the key
  belongs to. Set it to your Highflame login email (same email as your Tailscale login), and
  make sure you're a member of the **project the key is scoped to** — being an org admin
  without explicit project membership can be denied on older deployments.
- **You changed a policy but the result didn't change (and no new event in Observatory)** —
  Highflame dedupes repeated event ids. The scripts here stamp a unique `session_id` /
  `request_id` per run for exactly this reason; if you build your own payloads, do the same.
- **Policy deployed but commands still allowed** — check the **project picker**: the policy
  must be deployed in the same project your credential is scoped to (or account-wide). Also
  confirm mode is **enforce** — monitor records the deny but returns allow.
