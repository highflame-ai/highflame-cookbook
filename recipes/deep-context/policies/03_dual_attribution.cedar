// =============================================================================
// Dual Attribution — every privileged action names an agent AND a human
// =============================================================================
// "Which agent did this?" is half an answer. The other half is "on whose
// behalf?" An agent is not an accountable party; the person who pointed it at
// the work is. Shield projects both sides of that pair, so the requirement can
// be a policy rather than a reporting convention nobody enforces.
//
//   The agent (from the authenticated identity, NOT from the request body):
//     agent_id          String  e.g. "capvista-research-agent"
//     agent_type        String  "orchestrator" | "autonomous" | "tool_agent" | "human_proxy"
//     agent_trust_level String  "first_party" | "verified_third_party" | "unverified"
//     agent_framework   String  e.g. "langgraph", "claude-code", "crewai"
//     agent_publisher   String
//
//   The accountable human (from the ZeroID NHI claims on the credential):
//     principal         present only when the caller authenticated with a
//                       ZeroID agent credential. Absent for plain RS256 human
//                       tokens and internal-service callers.
//
// Both sides travel into Observatory on every event (`user_id` and
// `labels.agent_id` / `labels.agent_trust_level`), which is what makes the
// session timeline in the walkthrough attributable end to end instead of a
// list of anonymous decisions.
//
// ---------------------------------------------------------------------------
// ⚠️ Known platform drift — read before tightening these rules
// ---------------------------------------------------------------------------
// At runtime Shield projects `principal` as a nested RECORD
// (highflame-shield internal/scheduler/nhi.go buildPrincipalContext):
//
//     principal: { identity_type, sub_type, trust_level, framework, publisher,
//                  capabilities: Set<String>, scopes: Set<String>,
//                  delegation_depth: Long, act_sub, act_iss, mission_id,
//                  grant_type }
//
// `act_sub` is the accountable human — the RFC 8693 delegating party. That is
// the field you actually want for dual attribution.
//
// But the published guardrails schema declares `"principal"?: String`
// (highflame-policy schemas/guardrails/schema.cedarschema). So the precise
// rule you want —
//
//     unless { context has principal && context.principal has act_sub }
//
// — is rejected by schema validation when you save it, even though it is what
// the evaluator would actually do. Until the schema declares `principal` as a
// record, the rules below use the existence check `context has principal`,
// which is type-agnostic and behaves correctly under both shapes. It is a
// weaker statement ("a ZeroID principal is attached") than the one you want
// ("a named human is attached"), so treat it as the floor, not the ceiling.
//
// Same drift class, worth knowing: the guardrails schema comments list
// identity_type as "human" | "agent" | "service", while the projector emits
// "agent" | "application" | "mcp_server" | "service". A rule testing
// identity_type == "human" validates cleanly and then never fires.
//
// Context keys consumed:
//   - agent_id, agent_type, agent_trust_level
//   - principal (existence only — see the drift note above)
//   - tool_is_sensitive, tool_category
//
// Category:  agent-identity
// Namespace: Guardrails
// =============================================================================

// ---------------------------------------------------------------------------
// Section 1: No unattributed privileged action
// ---------------------------------------------------------------------------
//
// `unless` rather than `when`, deliberately. The rule has to fire when the
// attribution is ABSENT, and an absent key cannot be compared — so the escape
// hatch has to be the existence check, not a test on a value that may not be
// there at all.

@id("agent-identity.require-principal-for-sensitive-tools")
@name("Require an attached principal for sensitive agent actions")
@description("Blocks call_tool on a sensitive tool by an agent unless the request carries a ZeroID principal block identifying who the agent acts for.")
@severity("critical")
@tags("category:agent-identity,threat:accountability,detection:rule,surface:call-tool,scope:per-agent")
@reject_message("Tool execution blocked: this agent invoked a sensitive tool with no accountable principal attached. Every privileged agent action must name the party it acts for.")
forbid (
    principal,
    action == Guardrails::Action::"call_tool",
    resource
)
when {
    context has agent_id && context.agent_id != "" &&
    context has tool_is_sensitive && context.tool_is_sensitive == true
}
unless {
    context has principal
};

// ---------------------------------------------------------------------------
// Section 2: Trust level gates the blast radius
// ---------------------------------------------------------------------------

@id("agent-identity.block-unverified-agent-sensitive-tools")
@name("Block unverified agents from sensitive tools")
@description("Blocks call_tool when agent_trust_level is \"unverified\" and the tool is sensitive or dangerous.")
@severity("critical")
@tags("category:agent-identity,threat:accountability,detection:rule,surface:call-tool,scope:per-agent")
@reject_message("Tool execution blocked: unverified agents may not call sensitive or dangerous tools. Register and adopt the agent to raise its trust level.")
forbid (
    principal,
    action == Guardrails::Action::"call_tool",
    resource
)
when {
    context has agent_trust_level && context.agent_trust_level == "unverified" &&
    (
        (context has tool_is_sensitive && context.tool_is_sensitive == true) ||
        (context has tool_category && context.tool_category == "dangerous")
    )
};

// ---------------------------------------------------------------------------
// Section 3: Autonomous agents get a higher bar
// ---------------------------------------------------------------------------
//
// agent_type distinguishes an agent a human is actively driving
// ("human_proxy") from one running on its own ("autonomous"). Nobody is
// watching the second kind in real time, so a sensitive tool call from an
// autonomous agent should require first-party trust rather than merely
// "not unverified".

@id("agent-identity.restrict-autonomous-agent-sensitive-tools")
@name("Restrict sensitive tools for autonomous agents to first-party trust")
@description("Blocks call_tool on a sensitive tool when agent_type is \"autonomous\" unless agent_trust_level is \"first_party\".")
@severity("high")
@tags("category:agent-identity,threat:escalation,detection:rule,surface:call-tool,scope:per-agent")
@reject_message("Tool execution blocked: autonomous agents must be first-party to call sensitive tools. No human is in the loop to catch a mistake.")
forbid (
    principal,
    action == Guardrails::Action::"call_tool",
    resource
)
when {
    context has agent_type && context.agent_type == "autonomous" &&
    context has tool_is_sensitive && context.tool_is_sensitive == true
}
unless {
    context has agent_trust_level && context.agent_trust_level == "first_party"
};
