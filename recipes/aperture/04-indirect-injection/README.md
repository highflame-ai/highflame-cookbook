# 04 · Block indirect prompt injection

**The value:** *"Our agents read issues, docs, and tool output from sources we don't
control. A hidden instruction in any of them shouldn't be able to hijack the agent into
exfiltrating secrets."*

When an agent reads a poisoned document or tool result, that content rides back into its
*next* request to the model. Highflame inspects that request, spots the smuggled
instruction, and blocks it.

> **Why it works:** the guardrail evaluates the request going to the model — which now
> carries the poisoned content — so the hidden instruction is visible exactly when it would
> take effect.

**Try it in the demo app:** ask the agent to *"follow the setup steps in
[`docs/integrations.md`](https://github.com/highflame-ai/highflame-demo-app/blob/main/docs/integrations.md)"* —
the hidden `<!-- SYSTEM OVERRIDE … -->` instruction is caught.

---

## Set up the policy in Studio

1. **Studio → Code Agents → Tailscale Aperture** (one-time hook setup — see [the track setup](../README.md#one-time-setup)).
2. **Policies → New Policy → Guardrail.** Trigger on **prompt injection** (set the
   sensitivity threshold to your risk tolerance); action **block**; mode **enforce**;
   custom message — *"Highflame Security blocked a hidden instruction detected in
   tool/document content."*
   ![Injection policy](img/01-trigger-injection.png)
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
  "message": "Highflame Security blocked a hidden instruction detected in tool/document content."
}
```

## Verify

```bash
python smoke_test.py
```

Confirms the poisoned request is blocked.

---

## Notes

- The poisoned content is caught when it re-enters a request to the model — exactly what
  happens after an agent reads a file, issue, or page and continues. The script sends that
  follow-up request directly.
- Tune the injection sensitivity threshold in Studio to balance protection against false
  positives.
- The payload targets `evil.example`, a reserved, non-routable example domain.
