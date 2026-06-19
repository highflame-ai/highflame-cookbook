# 05 · Govern dangerous tools & shell

**Customer value:** *"Our agents run shell commands and call tools. A `curl | sh` from a
sketchy source, or an agent reaching for a destructive command, should be stopped — and we
want to know which tools our agents even use."*

**Integration:** Aperture-routed agents (Codex and others) re-send their conversation —
including prior tool calls — each turn. **Cerberus evaluates those tool calls synchronously**
on the `pre_request` hook ([cerberus#96](https://github.com/highflame-ai/highflame-cerberus/pull/96)),
so a dangerous command in the agent's history is caught at the LLM boundary: Shield's
**bash AST classifier** flags the `curl | sh` (network + execute) → `block`.

**Stage:** [`highflame-demo-vault/scripts/bootstrap.sh`](https://github.com/highflame-ai/highflame-demo-vault/blob/main/scripts/bootstrap.sh) (`curl … | sh`).

> **Two boundaries — read this.** Per [Aperture's guardrail docs](https://tailscale.com/docs/aperture/guardrails),
> guardrails fire at the **LLM request** boundary, **not** on the live outbound MCP/tool call.
> So two complementary controls:
> - **What this recipe shows:** dangerous tool calls *in the resent request* are blocked, and
>   Aperture `modify` can **strip risky tool declarations** from the `tools` array before the
>   model sees them.
> - **For execution-time gating** of the actual call, use **MCP grants** (limit which tools
>   Aperture exposes) or the **native IDE hook** (Overwatch `PreToolUse`). Don't rely on the
>   guardrail to police the outbound call itself.

---

## Track A — author the policy in Studio

1. **Studio → Code Agents → Tailscale Aperture** (one-time hook setup — see [the track README](../README.md#one-time-setup)).
2. **Policies → New Policy → Guardrail.** Trigger: detector `bash_ast_classifier` operation
   classes — forbid when `network_access` AND `execute_enabling` co-occur (the `curl | sh`
   shape), or use `tool_risk` for sensitive-tool + dangerous-arg patterns.
   ![Shell operation classes](img/01-trigger-shell.png)
3. **Action:** `forbid`. **Mode:** `enforce`.
   `@reject_message("Highflame Security has detected unauthorized shell access.")`
4. Save & activate, scoped to your account/project.

---

## Track B — see the decision

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

---

## Verify against prod

```bash
python smoke_test.py
```

Asserts the dangerous tool call is blocked.

---

## Notes & honesty

- **Tool-call capture covers agents that resend tool history** (Codex `input`, etc.). The
  payload here uses that shape. Coverage for additional agent transcript formats expands over
  time.
- **Discovery is half the value:** even in monitor mode, every tool call flows into Studio →
  Code Agents, giving you an inventory of which tools/commands your agents actually run before
  you write a single blocking policy.
- The command targets `evil.example` (reserved, non-routable).
