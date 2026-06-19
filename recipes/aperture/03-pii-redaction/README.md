# 03 · Redact PII (email) — scrub it, don't block it

**The value:** *"We don't want to block developers for using customer data — we want the
PII gone before it leaves our network. Keep them productive; scrub the address."*
Blocking is blunt; **redaction keeps the developer moving** while the sensitive value never
reaches the model.

**How it works:** Aperture's guardrail supports a **redact** outcome — Highflame returns a
scrubbed copy of the request and Aperture forwards *that* to the provider instead of the
original. The model answers usefully; it never receives the address. If a request can't be
safely scrubbed, Highflame blocks it instead — un-scrubbed PII is never forwarded.

**Try it in the demo app:** ask the agent to *"draft a follow-up email to the lead in
[`data/customers.csv`](https://github.com/highflame-ai/highflame-demo-app/blob/main/data/customers.csv)"* —
the email address is masked before the model sees it.

---

## Set up the policy in Studio

1. **Studio → Code Agents → Tailscale Aperture** (one-time hook setup — see [the track setup](../README.md#one-time-setup)).
   For a redaction guardrail used for compliance, set the Aperture hook `fail_policy` to
   **`fail_closed`** so an outage never forwards un-scrubbed PII.
2. **Policies → New Policy → Guardrail.** Trigger on **PII → email**; action **redact /
   mask**; mode **enforce**. The mask action is what makes Highflame return a scrubbed
   request instead of a block.
   ![Redact email policy](img/01-trigger-email.png)
3. Save & activate.

---

## See the redaction

```bash
cp .env.example .env        # set HIGHFLAME_API_KEY (the Aperture service key)
pip install -r requirements.txt
python aperture_event.py
```

```text
{
  "action": "modify",
  "request_body": {
    "model": "claude-opus-4-8",
    "messages": [
      { "role": "user", "content": "Draft a short follow-up email to our new lead. Their address is [REDACTED] — keep it under 80 words." }
    ]
  }
}
```

The `request_body` is exactly what Aperture sends upstream instead of the original — the
email never leaves your network.

## Verify

```bash
python smoke_test.py
```

Confirms the response redacts the email from the forwarded request.

---

## Notes

- Requires a redact-email policy active in your tenant. Without it, the script warns and
  skips rather than reporting a redaction that didn't happen.
- **Mask, replace, and full-redact** strategies are supported. Redaction applies to the
  user prompt; to govern PII inside tool-call arguments, pair it with a tool-call policy or
  MCP grants.
- **Block vs redact:** hard identifiers (SSNs, secrets) are a [block](../02-block-pii-ssn/);
  email and phone are better *scrubbed and forwarded* — that's this recipe.
- The email in the demo is fictional (`jane.doe@example.com`).
