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
// The two shapes answer different questions:
//   - max        = "did this session EVER cross a line?"  (one bad turn, remembered)
//   - cumulative = "how much total pressure has it applied?" (many small pushes)
//
// A stateless filter has neither number. At the moment the tool call arrives it
// sees one tool call, with no memory that the preceding ten minutes were spent
// working up to it.
//
// ---------------------------------------------------------------------------
// Measured on dev1 against the walkthrough's 6-turn conversation
// ---------------------------------------------------------------------------
// Values observed at the tool call that follows the conversation (reproduced
// identically across repeat runs):
//
//   session_max_jailbreak_score      97     ← Section 1 fires on this
//   session_max_injection_score      49
//   session_cumulative_risk_score   248     ← Section 2 fires on this
//   session_threat_turns              2     ← Section 3 fires on this
//
// All three sections fire on a six-turn conversation. That was NOT true before
// highflame-shield#549, and the difference is worth understanding, because it
// is the same lesson the whole recipe teaches.
//
// Until that shipped, jailbreak turns were scored but never recorded as
// detections, so this conversation ended with session_threat_turns == 0 while
// session_max_jailbreak_score sat at 97 — a rule on the counter validated
// cleanly and never fired. The same PR also found that cumulative risk was
// computed from the single-turn classifier alone, ignoring the deepcontext
// detector: this conversation accumulated 111, because the turns scoring 76
// and 97 on deepcontext read 0 and 23 on the classifier. With both fixed it
// accumulates 248.
//
// So the thresholds below are unchanged from the platform's existing
// multi-agent templates (a2a_security, multi_agent) — they were never the
// problem. The signal feeding them was.
//
// Context keys consumed:
//   - session_max_injection_score, session_max_jailbreak_score: Long
//   - session_cumulative_risk_score: Long
//   - session_threat_turns: Long
//   - tool_is_sensitive: Bool
//
// Requires highflame-shield#549 for Section 3 (and for Section 2 to reach its
// threshold on a conversation this short).
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
// This is the rule that turns the multi-turn detection into an enforcement
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
// max, yet the session as a whole has been steadily pushing. Threshold matches
// the platform's a2a_security profile, unchanged — the walkthrough reaches 248
// against it, comfortably over.

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
// The bar is 2 because that is the smallest number that distinguishes repeated
// from one-off, and a single detector hit is exactly the shape of a false
// positive. It is NOT tuned to this demo: the walkthrough's six turns produce
// 2 (turns 5 and 6, scoring 76 and 97), so the rule fires with nothing to
// spare. Long-running agent sessions accumulate turns faster and warrant a
// higher bar — the platform's multi_agent profile uses 6. Measure your own
// sessions in monitor mode before choosing.
//
// Requires highflame-shield#549: before it, jailbreak turns never incremented
// this counter, so on a pure-jailbreak escalation this rule was inert.

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
