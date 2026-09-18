// =============================================================================
// Session Risk Accumulation — history gates the action
// =============================================================================
// Policy 01 blocks the conversation. This one blocks the PAYOFF.
//
// A patient attacker expects some turns to be refused. What they actually want
// is one privileged action at the end — send the email, move the money, read
// the file. So the useful question at a tool call is not "is this tool call
// suspicious?" but "what has this conversation been doing up to now?"
//
// Shield accumulates that history on the session and projects it:
//
//   session_max_injection_score    Long  Highest injection score seen in ANY
//                                        turn of the session. A high-water
//                                        mark — it never decays, so quiet
//                                        turns cannot launder earlier ones.
//   session_max_jailbreak_score    Long  Same, for jailbreak.
//   session_cumulative_risk_score  Long  Uncapped SUM of per-turn risk. The
//                                        "death by a thousand cuts" counter.
//   session_threat_turns           Long  Count of turns that tripped a
//                                        detector — repetition, not severity.
//
// Three shapes, because attackers come in three shapes:
//   - max        = "did this session EVER cross a line?"   (one bad turn, remembered)
//   - cumulative = "how much total pressure has it applied?" (many small pushes)
//   - count      = "is this sustained, or a one-off?"       (repetition)
//
// A stateless filter has none of these numbers. At the moment the tool call
// arrives it sees one tool call, with no memory that the preceding ten minutes
// were spent working up to it.
//
// On the walkthrough's six-turn conversation, all three rules fire on the tool
// call that follows it: the session reaches a max jailbreak score of 97, a
// cumulative risk of roughly 250, and 2 threat turns. The clean-session control
// — the same tool call with no conversation behind it — passes all three.
//
// Thresholds match Highflame's multi-agent policy templates, so a tenant that
// later adopts those profiles gets one consistent risk scale rather than two.
//
// Context keys consumed:
//   - session_max_injection_score, session_max_jailbreak_score: Long
//   - session_cumulative_risk_score: Long
//   - session_threat_turns: Long
//   - tool_is_sensitive: Bool
//
// Requires: a stable session_id on every request, prompts AND tool calls. The
// tool call must ride the same session as the conversation or it reads 0.
//
// Compliance: OWASP LLM06, OWASP ASI01, ASI04
//
// Category:  agent-security
// Namespace: Guardrails
// =============================================================================

// ---------------------------------------------------------------------------
// Section 1: A session that ever crossed the line does not get to act
// ---------------------------------------------------------------------------
//
// This is the rule that turns multi-turn detection into an enforcement
// outcome. The conversation is what scored 97; the tool call is what gets
// stopped. An attacker who probes hard, is refused, goes quiet for five turns
// and then calmly asks for the tool is exactly what this rule is for.

@id("agent-security.block-tool-after-injection-in-session")
@name("Block tool use after an injection or jailbreak attempt in the session")
@description("Blocks call_tool when session_max_injection_score >= 60 or session_max_jailbreak_score >= 60 — an earlier turn in this session attempted injection or jailbreak.")
@severity("critical")
@tags("category:agent-security,threat:escalation,detection:aggregate,surface:call-tool,scope:multi-turn,owasp:llm01")
@reject_message("Tool execution blocked: an earlier turn in this session attempted prompt injection or jailbreak. Start a new session to use tools.")
forbid (
    principal,
    action == Guardrails::Action::"call_tool",
    resource
)
when {
    (context has session_max_injection_score && context.session_max_injection_score >= 60) ||
    (context has session_max_jailbreak_score && context.session_max_jailbreak_score >= 60)
};

// ---------------------------------------------------------------------------
// Section 2: Accumulated pressure gates sensitive tools
// ---------------------------------------------------------------------------
//
// Narrower than Section 1 (sensitive tools only) but triggered by a different
// shape of attack: one where no single turn ever scores high enough to set a
// max, yet the session as a whole has been steadily pushing.

@id("agent-security.block-sensitive-tool-on-session-risk")
@name("Block sensitive tools once the session has accumulated risk")
@description("Blocks call_tool when session_cumulative_risk_score >= 151 and tool_is_sensitive is true.")
@severity("high")
@tags("category:agent-security,threat:escalation,detection:aggregate,surface:call-tool,scope:multi-turn,owasp:asi01")
@reject_message("Tool execution blocked: this session has accumulated significant risk across earlier turns. Sensitive tools are withheld for the remainder of the session.")
forbid (
    principal,
    action == Guardrails::Action::"call_tool",
    resource
)
when {
    context has session_cumulative_risk_score &&
    context.session_cumulative_risk_score >= 151 &&
    context has tool_is_sensitive && context.tool_is_sensitive == true
};

// ---------------------------------------------------------------------------
// Section 3: Sustained probing, independent of any single score
// ---------------------------------------------------------------------------
//
// Neither a high-water mark nor a sum — just "how many turns tripped a
// detector". It catches the session that never spikes and never accumulates
// much, but keeps quietly testing the edges.
//
// The bar is 2 because that is the smallest number that separates repeated
// from one-off, and a single detector hit is exactly the shape of a false
// positive. It suits a chat-shaped session. Long-running agent sessions
// accumulate turns faster and warrant a higher bar — Highflame's multi-agent
// template uses 6. Run in monitor mode against your own traffic first, look at
// the distribution in Observatory, then choose.

@id("agent-security.block-tool-on-repeated-threat-turns")
@name("Block tool use in a session with repeated threat turns")
@description("Blocks call_tool when session_threat_turns >= 2 — more than one turn in this session tripped a detector.")
@severity("high")
@tags("category:agent-security,threat:escalation,detection:aggregate,surface:call-tool,scope:multi-turn,owasp:asi04")
@reject_message("Tool execution blocked: more than one turn in this session tripped a detector. This is sustained probing, not a one-off false positive.")
forbid (
    principal,
    action == Guardrails::Action::"call_tool",
    resource
)
when {
    context has session_threat_turns && context.session_threat_turns >= 2
};
