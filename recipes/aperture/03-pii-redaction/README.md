# 03 · Redact PII (email) — transparent scrub via Aperture `modify`

**Customer value:** *"We don't want to block developers for using customer data — we want
the PII gone before it leaves our network. Keep them productive; scrub the address."*
Blocking is blunt; **redaction keeps the developer moving** while the sensitive value never
reaches the model.

**How it works:** Aperture's `pre_request` guardrail supports a **`modify`** action — it
forwards a *replacement* request body. Shield's `pii` detector flags the email and a Cedar
`forbid` carrying `@redaction_strategy("mask")` scrubs it; **Cerberus returns
`{"action":"modify","request_body":…}`** with the email replaced. Aperture forwards the
scrubbed prompt to the provider. The model answers usefully; it never received the address.

> This is the recipe the Cerberus `modify` exposure unblocked — Cerberus rewrites the
> prompt inside `request_body` from Shield's `redacted_content`, and **fails safe to block**
> if the body can't be rewritten, so un-scrubbed PII is never forwarded.

**Stage:** [`highflame-demo-vault/contacts.json`](https://github.com/highflame-ai/highflame-demo-vault/blob/main/contacts.json) (planted fake leads).

---

## Track A — author the policy in Studio

1. **Studio → Code Agents → Tailscale Aperture** (one-time hook setup — see [the track README](../README.md#one-time-setup)).
   For a redaction guardrail used for compliance, set the Aperture hook `fail_policy` to
   **`fail_closed`** so a Highflame outage never forwards un-scrubbed PII.
2. **Policies → New Policy → Guardrail.** Trigger: detector `pii`, type `email`.
   ![PII email trigger](img/01-trigger-email.png)
3. **Action:** *Redact / Mask* — strategy `mask`. This is what makes Cerberus return
   `modify` instead of `block`.
   ![Redact action](img/02-action-mask.png)
4. **Mode:** `enforce`. Save & activate, scoped to your account/project.

---

## Track B — see the redaction

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

Highflame redacted the prompt; Aperture forwards -> 'Draft a short follow-up email to our new lead. Their address is [REDACTED] — keep it under 80 words.'
```

The `request_body` is exactly what Aperture sends upstream instead of the original — the
email never leaves your network.

---

## Verify against prod

```bash
python smoke_test.py
```

Asserts the response is `modify` and the email is **absent** from the forwarded body.

---

## Notes & honesty

- **Needs the Cerberus `modify` exposure deployed** (the `pre_request` redaction path) and a
  redact-email policy active in your tenant. Without the policy, the smoke test `WARN`s
  (got `allow`/`block`) rather than pretending PII was scrubbed.
- **`mask` / `replace` / `redact`** ship; `anonymize` is roadmap. Redaction-driven `modify`
  is currently scoped to the **user-prompt** surface (not tool-call arguments).
- **Block vs redact:** hard identifiers (SSN, secrets) are a [block](../02-block-pii-ssn/);
  email/phone are better *scrubbed and forwarded* — that's this recipe.
- Email here is fictional (`jane.doe@example.com`).
