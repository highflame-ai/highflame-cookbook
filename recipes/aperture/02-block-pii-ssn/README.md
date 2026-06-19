# 02 · Block PII — SSN / national ID

**The value:** *"A developer summarizing a customer export shouldn't be able to ship SSNs
to a model provider. Stop it at the edge, with a message that says why."*

Highflame detects national IDs and blocks the request with your branded message before it
reaches the provider.

**Try it in the demo app:** ask the agent to *"add an endpoint that exports all customers
as CSV"* — it pulls
[`data/customers.csv`](https://github.com/highflame-ai/highflame-demo-app/blob/main/data/customers.csv),
and the SSNs are blocked.

---

## Set up the policy in Studio

1. **Studio → Code Agents → Tailscale Aperture** (one-time hook setup — see [the track setup](../README.md#one-time-setup)).
2. **Policies → New Policy → Guardrail.** Trigger on **PII → national ID (SSN)**; action
   **block**; mode **enforce**; custom message — *"Highflame Security has blocked your
   prompt because it contained a national ID (SSN)."*
   ![PII national-ID policy](img/01-trigger-ssn.png)
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
  "message": "Highflame Security has blocked your prompt because it contained a national ID (SSN)."
}
```

## Verify

```bash
python smoke_test.py
```

Confirms the SSN prompt is blocked.

---

## Notes

- **Same setup, different trigger** as [01](../01-block-secrets/): only the policy's trigger
  changes (secrets → PII / SSN). The Aperture wiring is identical.
- Make sure the policy is active in enforce mode and your tenant's baseline authorization
  policy is loaded; the script warns and skips its assertion otherwise.
- **Block vs redact:** a national ID is a hard block. For PII you'd rather *scrub and
  forward* (email, phone), see [03 · redaction](../03-pii-redaction/).
- SSNs in the demo are fictional (`123-45-6789` and the SSA-reserved `987-65-432x` range).
