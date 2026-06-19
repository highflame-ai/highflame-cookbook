# 02 · Block PII — SSN / national ID

**Customer value:** *"A developer summarizing a customer export shouldn't be able to ship
SSNs to a model provider. Stop it at the edge, with a message that says why."*

**Integration:** Tailscale **Aperture** `pre_request` guardrail → Cerberus → Shield. Shield's
`pii` detector flags the national ID → Cedar `forbid` with your `@reject_message` → `block`.

**Stage:** [`highflame-demo-vault/customers.csv`](https://github.com/highflame-ai/highflame-demo-vault/blob/main/customers.csv) (planted fake SSNs).

---

## Track A — author the policy in Studio

1. **Studio → Code Agents → Getting Started → Tailscale Aperture** (one-time hook setup — see [the track README](../README.md#one-time-setup)).
2. **Policies → New Policy → Guardrail.** Trigger: detector `pii`, type `ssn` (national ID).
   ![PII national-ID trigger](img/01-trigger-ssn.png)
3. **Action:** `forbid`. **Mode:** `enforce`.
   `@reject_message("Highflame Security has blocked your prompt because it contained a national ID (SSN).")`
   ![Block + reject message](img/02-block-message.png)
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
  "message": "Highflame Security has blocked your prompt because it contained a national ID (SSN)."
}
```

---

## Verify against prod

```bash
python smoke_test.py
```

Asserts the SSN prompt is blocked. This is what the cookbook's scheduled CI runs against a
canary tenant.

---

## Notes & honesty

- **Same hook, different detector** as [01](../01-block-secrets/): only the Shield policy
  trigger changes (`secrets` → `pii`/`ssn`). The Aperture wiring is identical.
- The policy must be active in enforce mode (Track A), with a tenant Overwatch
  baseline-permit loaded; otherwise the smoke test `WARN`s instead of lying.
- **Block vs redact:** SSN is a hard block. For PII you'd rather *scrub and forward*
  (email, phone), see [03 · redaction](../03-pii-redaction/).
- SSNs here are fictional (`123-45-6789` and the SSA-reserved `987-65-432x` range).
