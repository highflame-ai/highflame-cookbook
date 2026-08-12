# 03 · DLP — regulated data & credentials, on every surface, in your formats

**The value:** _"We handle PHI, clinical data, and internal study identifiers. A guardrail that only reads the user's prompt is half a control — data leaks in the model's answer and in what tools hand back too. And it has to understand_ our _formats: our case IDs, our brand-restricted drug names — not just generic SSNs."_

This track covers use cases 10 and 11.
The runnable proof — [`dlp_guardrails.py`](dlp_guardrails.py) — catches a fictional MRN in a prompt, a credential in a model output, an MRN in a tool result, and (once provisioned) an internal `EXL-####` case id.

| UC  | Claim                                                                              | Verdict                                        |
| --- | ---------------------------------------------------------------------------------- | ---------------------------------------------- |
| 10  | Catch regulated data & credentials in prompts **and** outputs **and** tool results | 🟢 Supported (secrets block-only)              |
| 11  | Custom regex + keyword libraries for internal formats                              | 🟡 Partial (engine yes; Studio UI + a footgun) |

**Policy prerequisite:** the **Structural PII** (`privacy.defaults`) and **Secrets Detection** (`data-protection.defaults`) packs, in enforce (or monitor) mode.
`privacy.defaults` ships a HIPAA-tagged medical-identifier rule whose action list already covers `process_prompt`, `call_tool`, `read_file`, and `write_file` — which is why one rule covers all three surfaces.

---

## Run the proof

```bash
cd recipes/exelixis-pov
cp .env.example .env          # set HIGHFLAME_API_KEY
pip install -r requirements.txt
python 03-dlp/dlp_guardrails.py
```

All identifiers are fictional (an invented MRN, AWS's documented example key, an invented `EXL-####`).
**Never put real Exelixis PHI or credentials into a prompt.**

---

## UC10 · Every surface — supported

Highflame detects on three surfaces, each proven by the script:

- **Prompt** (`content_type="prompt"`) — the chart note with an MRN is caught on the way in.
- **Model output** (`content_type="response"`) — a credential the model was coaxed into echoing is caught on the way _out_. This is the egress path; streaming responses are buffered, scanned, and re-streamed.
- **Tool output** (`action="call_tool"`, `content_type="response"`) — a CRM row carrying an MRN back toward the model is caught by the _same_ medical-identifier policy.

**Redaction, not just blocking.** For PII/PHI, flip a rule's effect to `mask` / `replace` / `redact` / `anonymize` (Studio → Policies → the rule's effect dropdown) and the decision becomes `modify`: the MRN is masked, the model still answers usefully, and the raw value never leaves the tenant.

**The caveats the client should hear up front:**

- **Secrets are block-only.** A detected credential is stopped, never masked-and-forwarded — a `mask` effect on a secrets rule silently degrades to a clean allow. PII/PHI is fully redactable; credentials are not. Tracked as G-UC10.
- **Files are blocked, not redacted.** A redact verdict on an uploaded PDF/DOCX escalates to a hard block (the extracted text doesn't line up with the raw bytes to patch). Clinical PDFs are stopped, not scrubbed.
- **Detectors run only when a policy references them.** Install the PII/Secrets packs before the demo.

The detector coverage is deep for pharma: alongside SSN/credit-card/credential families, the PII detector ships `medical_record` (MRN), `patient_record`, `medicare_beneficiary_id`, `npi`, `medical_term` (oncology vocabulary), and `blood_type`, all context-scored so they fire inside genuine clinical text rather than on stray digits, plus an ML PII model and Microsoft Purview/MIP sensitivity-label awareness.

## UC11 · Custom formats — partial

**The engine is fully supported.** Custom regex patterns and keyword libraries are per-tenant, hot-reloaded, and need no code change or redeploy.
A custom pattern participates fully in the redaction pipeline — you can block _or_ mask an `EXL-####` id exactly like a built-in type.

**The two edges to plan around:**

1. **No Studio UI for custom regex yet** — you provision it via the Admin policy API (`POST /v2/admin/policy`, `category: "pii_types"`).
   Keyword libraries _do_ have a Studio UI (Detection Hub → keyword → Configure), but only substring + category are honored today — the UI's "regex" match mode and per-entry severity are inert, so use substring keyword matching.
2. **The write REPLACES the built-in pattern set** — it does not merge (on current `main`).
   Adding one custom regex naively deletes all 70+ built-in PII patterns (and thus breaks UC10).
   Until the fix lands, **read-modify-write:** fetch the current effective pattern set (a `dryrun` guard call returns it), append your pattern, and post the whole list back.
   Being closed by [highflame-shield #381](https://github.com/highflame-ai/highflame-shield/pull/381), which adds an `extends_defaults: true` flag so custom entries layer on top of the built-ins (and override by name) — turning the demo into a one-line `{"extends_defaults": true, "entries": [...]}` config.

**Provisioning `EXL-####` (Admin API):**

```jsonc
POST /v2/admin/policy
{
  "policy_name": "Exelixis Internal Identifiers",
  "policy_type": "detection_rule",
  "category":    "pii_types",
  "content": "{\"entries\": [ /* the existing baseline entries, then: */
     {\"name\": \"exelixis_case_id\", \"pattern\": \"\\\\bEXL-\\\\d{4}\\\\b\", \"base_score\": 1.0},
     {\"name\": \"exelixis_protocol_id\", \"pattern\": \"(?i)\\\\bPROTO-[A-Z]{2}\\\\d{5}\\\\b\",
      \"base_score\": 1.0, \"context_keywords\": [\"protocol\",\"trial\",\"study\"], \"context_boost\": 0.15}
  ]}"
}
```

Then author a Cedar rule that blocks (or masks) when `context.pii_types.contains("exelixis_case_id")`, deploy, and the script's UC11 step starts catching `EXL-4471`.
Regex is Go RE2 — no backreferences or lookahead; pre-validate any pattern.
Set `EXELIXIS_CASE_ID_REGEX` in `.env` to match your real internal format.

Building a first-class **custom-patterns UI in Studio** and a **merge-not-replace** semantics are tracked as G-UC11.

---

## Verify

```bash
python 03-dlp/smoke_test.py
```

Confirms an MRN in a prompt and a credential in a model output are both caught.
