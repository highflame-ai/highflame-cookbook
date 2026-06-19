# 04 · Block indirect prompt injection

**Customer value:** *"Our agents read issues, docs, and tool output from sources we don't
control. A hidden instruction in any of them shouldn't be able to hijack the agent into
exfiltrating secrets."*

**Integration:** Tailscale **Aperture** `pre_request` guardrail → Cerberus → Shield. The
poisoned content (a hidden instruction in `docs/integration.md`) rides back into the *next*
LLM request after the agent reads it; Aperture inspects that request and Shield's
`injection` detector fires → `block`.

> **The boundary that matters:** Aperture guardrails evaluate the **LLM request** — which now
> carries the poisoned tool/doc output — not the original benign prompt. That's exactly where
> indirect injection becomes visible. (Aperture does *not* intercept the outbound tool call
> itself; it catches the smuggled instruction when it re-enters the model request.)

**Stage:** [`highflame-demo-app/docs/integrations.md`](https://github.com/highflame-ai/highflame-demo-app/blob/main/docs/integrations.md) (hidden `<!-- SYSTEM OVERRIDE … -->` payload).

---

## Track A — author the policy in Studio

1. **Studio → Code Agents → Tailscale Aperture** (one-time hook setup — see [the track README](../README.md#one-time-setup)).
2. **Policies → New Policy → Guardrail.** Trigger: detector `injection` (prompt injection),
   threshold at your risk tolerance.
   ![Injection trigger](img/01-trigger-injection.png)
3. **Action:** `forbid`. **Mode:** `enforce`.
   `@reject_message("Highflame Security blocked a hidden instruction detected in tool/document content.")`
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
  "message": "Highflame Security blocked a hidden instruction detected in tool/document content."
}
```

---

## Verify against prod

```bash
python smoke_test.py
```

Asserts the poisoned request is blocked.

---

## Notes & honesty

- **The poisoned content must re-enter an LLM request** for the Aperture guardrail to see it
  — which is exactly what happens when an agent reads a file/issue/page and continues the
  turn. This recipe sends that follow-up request directly.
- The ML `injection` detector is what fires here; tune the threshold in Studio. Deeper
  multi-turn (`deepcontext`) detection is improving — the canonical single-shot injection is
  what this recipe demonstrates.
- The payload targets `evil.example` (a reserved, non-routable example domain).
