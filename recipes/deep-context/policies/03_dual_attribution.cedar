// =============================================================================
// Dual Attribution — every privileged action names an agent AND a human
// =============================================================================
// "Which agent did this?" is half an answer. The other half is "on whose
// behalf?" An agent is not an accountable party; the person who pointed it at
// the work is. Shield projects both sides of that pair, so the requirement can
// be a policy rather than a reporting convention nobody enforces.
//
//   The agent (from the authenticated identity, NOT from the request body):
//     agent_id          String  e.g. "research-agent"
//     agent_type        String  "orchestrator" | "autonomous" | "tool_agent" | "human_proxy"
//     agent_trust_level String  "first_party" | "verified_third_party" | "unverified"
//     agent_framework   String  e.g. "langgraph", "claude-code", "crewai"
//     agent_publisher   String
//
//   The accountable human (from the identity claims on the credential):
//     principal         Present when the caller authenticated with a
//                       registered agent credential. Absent for plain user
//                       tokens and internal-service callers.
//
// Both sides travel into Observatory on every event (`user_id` and
// `labels.agent_id` / `labels.agent_trust_level`), which is what makes the
// session timeline attributable end to end rather than a list of anonymous
// decisions.
//
// Section 1 is the rule worth adopting even if you adopt nothing else here:
// an agent may not take a privileged action that cannot be attributed to a
// principal. It turns "we can trace it" into "it cannot happen untraced."
//
// Context keys consumed:
//   - agent_id, agent_type, agent_trust_level
//   - principal (existence)
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
@description("Blocks call_tool on a sensitive tool by an agent unless the request carries a principal identifying who the agent acts for.")
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
//
// A service key authenticates as "unverified" until the agent is registered
// and adopted in Studio. Run this policy in MONITOR mode until then: in
// enforce mode this rule blocks every sensitive tool call from an unverified
// agent — including legitimate ones. Monitor mode records what it would have
// blocked on every event, so Observatory shows the full picture while nothing
// breaks. Register the agent, then switch to enforce.

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
