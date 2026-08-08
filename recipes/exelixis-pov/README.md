# Exelixis PoV — end-to-end cookbook

This track maps the twelve PoV use cases Exelixis put forward onto Highflame, one runnable proof at a time.
Each use case has a verdict — **supported**, **partial**, or **gap** — decided by reading the platform's own code, its capability spec, and a live tenant, not by reading a datasheet.
Where a use case is fully supported you get a script that proves it in seconds.
Where it is partial, the recipe proves the part that works and says plainly where the edge is.
Where it is a genuine gap, we do not fake it: [`GAP-ANALYSIS.md`](GAP-ANALYSIS.md) turns each gap into a scoped engineering work item with a landing repo and effort.

> **Honesty is the point of a PoV.** A capability marked "partial" that we demo cleanly and describe accurately builds more trust than a "supported" that falls over when the client's security team pushes on it.
> Every claim below is traceable to code; nothing here rides on a `planned` capability being presented as shipped.

---

## The twelve use cases at a glance

| #   | Use case (Exelixis wording, abbreviated)                                           | Verdict       | Where                            |
| --- | ---------------------------------------------------------------------------------- | ------------- | -------------------------------- |
| 1   | Discover all agents — in-house, third-party, **and shadow** — across clouds & SaaS | 🟡 Partial    | [01](01-identity-orchestration/) |
| 2   | Every agent gets a **unique** identity, not a shared key                           | 🟢 Supported  | [01](01-identity-orchestration/) |
| 3   | Sub-agents **cannot inherit more authority** than their parent                     | 🟢 Supported  | [01](01-identity-orchestration/) |
| 4   | Agents get **short-lived, task-scoped** credentials, not standing access           | 🟡 Partial    | [01](01-identity-orchestration/) |
| 5   | Revoking a parent identity **collapses the whole delegation tree**                 | 🟢 Supported  | [01](01-identity-orchestration/) |
| 6   | A **traceable chain**: human → workflow → orchestrator → sub-agent → tool call     | 🟡 Partial    | [01](01-identity-orchestration/) |
| 7   | Every tool call, model request, and A2A hop is **checked before execution**        | 🟢 Supported¹ | [02](02-authorization/)          |
| 8   | An agent acting for a **deactivated human** is automatically denied                | 🔴 Gap²       | [02](02-authorization/)          |
| 9   | Detect **mid-execution objective redirection**                                     | 🟡 Partial    | [02](02-authorization/)          |
| 10  | DLP catches regulated data & credentials in **prompts and outputs**                | 🟢 Supported³ | [03](03-dlp/)                    |
| 11  | **Custom regex + keyword libraries** for internal formats                          | 🟡 Partial    | [03](03-dlp/)                    |
| 12  | Direct + **indirect** injection, plus **MCP tool-description poisoning**           | 🟡 Partial    | [04](04-injection-supply-chain/) |

¹ Model requests and MCP tool calls are enforced pre-execution today. A2A (agent-to-agent) hops are checked, but only as a coerced `process_prompt` text scan — there is no A2A-native policy action yet. See track 02.
² The _mechanism_ — revoke an identity and its entire delegation tree dies within seconds — is fully built and demoed in track 01. What is missing is the _trigger_: nothing today maps a human's deactivation in the IdP to that revocation. That wiring is the single highest-value gap for this PoV. See track 02 and `GAP-ANALYSIS.md` (G-UC8).
³ With one caveat the client should hear up front: **credentials are block-only, not redactable** — a secret is stopped, never masked-and-forwarded. PII/PHI is fully redactable. See track 03.

**Score:** 5 supported, 6 partial, 1 gap.
Every "partial" has a working demo of its supported half and a named, scoped path to close the rest.

---

## Why this track exists (the Exelixis frame)

Exelixis is evaluating Highflame as the identity, authorization, and data-protection layer for AI agents operating on regulated pharma data — clinical, PHI, and internal study identifiers.
The twelve use cases split into four themes, and this track follows Exelixis's own grouping:

| Track                                                           | Theme                                                                                            | Use cases        |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ---------------- |
| [**01 · Identity Orchestration**](01-identity-orchestration/)   | Discover, uniquely identify, delegate, scope, revoke, and trace agents                           | 1, 2, 3, 4, 5, 6 |
| [**02 · Authorization**](02-authorization/)                     | Check every action against policy before it runs; deny revoked principals; catch objective drift | 7, 8, 9          |
| [**03 · DLP**](03-dlp/)                                         | Catch regulated data & credentials on every surface; configure custom formats                    | 10, 11           |
| [**04 · Injection & Supply Chain**](04-injection-supply-chain/) | Direct + indirect prompt injection; MCP tool-description poisoning                               | 12               |

---

## What you need

- **A tenant to evaluate against.** These recipes run against live Highflame SaaS by default. Point them at any environment with the `HIGHFLAME_*_URL` variables in `.env`.
- **One service key.** A ZeroID service key (`zid_sk_...`) from Studio → Settings → API Keys. Every script reads it from `HIGHFLAME_API_KEY` and **skips cleanly if it is absent** — nothing runs against a real tenant by accident.
- **Python 3.10+.** The scripts use only the standard library; `python-dotenv` is an optional convenience.

```bash
cd recipes/exelixis-pov
cp .env.example .env          # paste your zid_sk_ key into HIGHFLAME_API_KEY
pip install -r requirements.txt
```

Each track's README has its own Studio click-path and its runnable proof.
The shared engine is [`common.py`](common.py): it exchanges your key for a short-lived token (the identity proof) and calls Shield's decision endpoint (the enforcement proof).
Read it once and every recipe reads the same way.

---

## How a recipe reads

Two moves, repeated:

1. **Mint a token.** `common.mint_token()` exchanges your `zid_sk_` key for a short-lived access token at the AuthN token endpoint. The _decoded claims of that token_ are the proof for the identity use cases — a unique subject, a one-hour expiry, the scopes it may use, the human who owns it.
2. **Ask before acting.** `common.guard()` sends content to Shield with a Cedar action and reads back `allow` / `deny` / `modify`. This is a **pre-execution** decision — the caller acts on the verdict _before_ it forwards anything to a model or a tool. That is the whole point of use case 7, and every DLP and injection recipe is a specialization of it.

Run any track's proof, then verify it in the product:

```bash
python 01-identity-orchestration/identity_lifecycle.py
python 02-authorization/pre_execution_and_revocation.py
python 03-dlp/dlp_guardrails.py
python 04-injection-supply-chain/injection_and_poisoning.py
```

Every decision is attributed and recorded — open **Studio → Observatory** to see the same request in the agent's trace, with the policy that fired.

---

## Running the PoV: preparation notes

A few things to lock in before the evaluation call, so a demo never fails for an avoidable reason:

- **Detectors only run when a policy references them.** Shield schedules a detector only if an active Cedar policy reads one of its signals (`optimize=true`, scoped per action). Install the relevant policy pack **before** the demo, or the signal will simply be absent. Each track README names the packs it needs.
- **Start in monitor, promote to enforce.** Every policy has a mode. Monitor records a would-block while still allowing the request; enforce returns the block. The scripts read the _real_ verdict either way (`actual_decision`), so you can demo against a monitor-mode tenant safely and flip to enforce when ready.
- **Use a clean project.** Shield evaluates one policy engine per scope; a stray "baseline permit" or a duplicate monitor-mode rule will muddy a result. Run the PoV in a fresh project.
- **Fake data only.** Every identifier in these recipes is invented — SSA-reserved SSNs, AWS's documented example keys, `example.com` addresses, invented MRNs and `EXL-####` study ids. **Never put real Exelixis PHI or credentials into a prompt**, in a PoV or otherwise.

---

## The gaps, and what closing them takes

Six use cases are partial and one is a gap.
[`GAP-ANALYSIS.md`](GAP-ANALYSIS.md) is the engineering companion to this cookbook: every gap becomes a work item with the repo it lands in, the capability-spec entry it needs, a rough size, and whether it blocks the PoV or is a fast-follow.
The three that most shape the Exelixis conversation:

- **UC8 — human-deactivation → agent denial (gap).** The revocation cascade is built; the IdP trigger is not. Closing it is a webhook/SCIM adapter plus an owner-scoped revoke — an integration, not a new enforcement engine.
- **UC1 — traffic-based shadow-agent detection (partial).** We discover agents the IdP already knows about; we do not yet flag an agent seen only in gateway traffic that is in no registry. Design exists (ADR 0027); it is not built.
- **UC9 — semantic objective-drift detection (partial).** We catch a redirect phrased as an injection today; we do not yet measure semantic distance from the session's original objective. The anchor is already captured; the comparator is the missing piece (CAP-DET-002).

None of these are presented as working in the recipes. That is deliberate.
