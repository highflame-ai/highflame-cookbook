# LangGraph + MCP · a SOC triage team with identity, authorization, and CIBA step-up

**The value:** *"Our agents don't just read and summarize — they act. Before we let a
multi-agent workflow touch the firewall, we need every agent to have its own identity,
every tool call authorized against that identity, and a human approval — on the
analyst's own terms — in front of the one action we can't take back."*

This demo is a four-agent **SOC log-triage team** on one LangGraph graph, working a
seeded alert: a workstation beaconing to a rare external host. Three MCP servers carry
all capability (logs, threat intel, firewall), one more is deliberately left ungoverned,
and a single triage run exercises **all three AARM disposition classes** — proceeded,
blocked, suspended.

| Agent | Identity path | Chain evidence | Scopes |
| --- | --- | --- | --- |
| **soc-supervisor** | RFC 8693 exchange over the analyst's login | `act.sub` = the human analyst | `triage:*` |
| **log-collector** | `api_key` grant, `created_by`=supervisor | ZeroID registry metadata | `tools:logs:read` |
| **threat-analyst** | `api_key` grant, `created_by`=supervisor | ZeroID registry metadata | `tools:intel:read` |
| **responder** | RFC 8693 **with `actor_token`** | `act.sub` chain in the token itself | `tools:firewall:write` |

Two delegation paths, on purpose. The read-only workers are ephemeral, in-process
workloads — the cheap attenuated-identity pattern is the *correct* one for them. The
responder takes the one privileged action, so it carries the cryptographic chain.
Every identity resolves to a WIMSE URI and the run prints it at each hop.

## The beats, in run order

1. **`allow`** — the collector queries flows/DNS through the fronted `soc-logs` MCP
   server. Every span carries the delegation attributes (`hf.nhi.delegation_depth`,
   `hf.nhi.delegated_by`, `hf.principal_type: agent`).
2. **`modify`** — the auth log contains employee emails. The PII policy runs in modify
   mode: the tool result comes back **redacted at HTTP 200**. Redaction is an
   allow-class outcome — the triage proceeds on redacted data instead of being blocked.
3. **`deny`, twice** — the threat-analyst oversteps, scripted so it happens every run:
   - **Issuance layer:** it asks AuthN for `tools:firewall:write` via token exchange.
     The triple scope intersection (requested ∩ delegator ∩ allowed) refuses to widen.
     No capable token ever exists.
   - **Runtime layer:** it calls `block_ip` with its own token anyway. Cedar answers
     403 with the determining policy id (`policies/tool-scope.cedar`).
4. **`step_up`** — the responder calls `block_ip`. The policy carries
   `@step_up_required("soc_lead")`, so Shield answers `decision: step_up` and fires the
   CIBA backchannel. Studio's approval pane shows the `binding_message` — *"C2
   beaconing from ws-114, verdict confirmed-c2"* — plus the typed
   `authorization_details`. The run polls the CIBA token grant, visibly
   (`pending... pending... APPROVED`), retries on the upgraded token, and the block
   executes. **Deny in the pane, or let it expire, and the action stays refused —
   fail-closed.** The approval receipt lands next to the action, keyed to the
   approver's `sub`.
5. **Shadow MCP** — the threat-analyst also calls `geoip-community`, a server this
   recipe deliberately does **not** register. The calls work, and nothing about them
   is governed. In Studio's MCP coverage view it surfaces as **shadow** — the
   ungoverned surface, named — while the other three servers show as covered. Don't
   "fix" it by registering it; the gap is the feature.

## Set it up in Studio

1. **API key** — Studio → Settings → API Keys → create a key for this recipe's tenant.
2. **Approver** — nothing to create. The `soc_lead` string in the policy is a targeting
   label (it rides the CIBA request as `group_hint`); today Studio's approval pane
   delivers every prompt tenant-wide, so being logged into the tenant is what makes
   you the approver. First approver wins. When AuthN's role store lands, this same
   name becomes deploy-validated and delivery becomes role-scoped — the policy file
   won't change.
3. **Policies** — the three files in [`policies/`](./policies) are the reference
   copies: the `@step_up_required("soc_lead")` gate on `block_ip`, the per-agent
   tool-scope forbid, and the delegation-depth cap. Add a **PII policy in modify
   mode** for the redaction beat.
4. **MCP registry** — register `soc-logs`, `threat-intel`, and `edge-firewall`.
   Leave `geoip-community` out (see beat 5).

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in HIGHFLAME_API_KEY and OPENAI_API_KEY
python graph.py        # keep Studio's approval pane open in a browser
```

When the run pauses at `[step-up] waiting on the soc_lead approval pane`, switch to
Studio and click **approve** (run it again and click **deny** to see the refusal
path; or just wait out the expiry for the fail-closed timeout).

`python smoke_test.py` asserts the two gates headlessly (no approver in CI): the
analyst's `block_ip` must not proceed, and the responder's must come back `step_up`.

## What to show in Observatory

- **Four sessions, one case** — each agent is its own principal; the session ids share
  the alert id. This is the "which human is behind this tool call" answer, per hop.
- **The deny** with its determining policy id on the threat-analyst's session.
- **The approval receipt** on the responder's session, linked by `correlation_id`,
  committing to the approver's `sub` claim.
- **MCP coverage** — three covered servers, one shadow row.

## Honest edges (read before demoing)

- **The approval pane is the delivery channel.** Step-up approval delivery is scoped
  to Studio today — no Slack/email push yet. Plan the demo with Studio on screen.
- **Two identity capabilities are still rolling out** and the recipe degrades
  gracefully around both, printing `DEGRADED` in the identity printout when it does:
  - Registering the responder's actor-assertion key **after** identity creation is not
    yet available — register the key at creation time, or run without
    `HIGHFLAME_RESPONDER_ASSERTION` and lose only the `act.sub` printout.
  - Without `HIGHFLAME_ANALYST_TOKEN` (a PKCE login token), the human hop of the
    chain is skipped and the supervisor runs on the service-key identity.
- **The scripted overreach is scripted.** Beats 3a/3b are deliberate demo code, not
  emergent model misbehavior — a demo must show the refusal every run. Say so when
  presenting; the enforcement being exercised is real either way.
