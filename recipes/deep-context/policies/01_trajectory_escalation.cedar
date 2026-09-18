// =============================================================================
// Multi-Turn Trajectory Escalation  (stop the attack no single message reveals)
// =============================================================================
// Shield runs two independent injection/jailbreak analyses and projects them
// as SEPARATE Cedar context keys:
//
//   injection_pulse_score         0-100  Pulse — single-turn classifier.
//                                        Sees ONLY the current message.
//   injection_deep_context_score  0-100  DeepContext — stateful GRU that
//                                        carries hidden state across turns,
//                                        keyed on session_id.
//   injection_score               0-100  MAX(pulse, deep_context). What the
//                                        platform default policies consume.
//
// (Same three for jailbreak_*.)
//
// A "crescendo" attack exploits exactly this gap. No single message is
// alarming — each turn is a small, plausible step — but the TRAJECTORY is an
// attack. A stateless content filter scores every turn in isolation and
// therefore scores every turn low. That is not a tuning failure; a filter
// with no memory has nothing to be alarmed about.
//
// Section 1 is the rule that matters: it fires on the DIVERGENCE between the
// two scores. High deep-context, low pulse means, literally, "the history is
// an attack and this message is not." Nothing that scores one message at a
// time can express that condition, because it only ever has one number.
//
// Section 2 is a plain safety net at a higher deep-context threshold, for the
// case where the trajectory becomes blatant enough that pulse catches up too.
//
// Context keys consumed:
//   - multi_turn_detection:           Bool  (true only when threaded state was used)
//   - injection_deep_context_score:   Long (0-100)
//   - injection_pulse_score:          Long (0-100)
//   - jailbreak_deep_context_score:   Long (0-100)
//   - jailbreak_pulse_score:          Long (0-100)
//   - conversation_turn:              Long
//
// Requires: the `deepcontext` detector enabled, AND a stable session_id on
// every request in the conversation. With no session_id there is no threaded
// state, multi_turn_detection is false, and none of these rules can fire.
//
// Compliance: OWASP LLM01, OWASP LLM02; MITRE ATLAS AML.T0051, AML.T0054
//
// Category:  security
// Namespace: Guardrails
// =============================================================================

// ---------------------------------------------------------------------------
// Section 1: Trajectory/turn divergence — the exclusive capability
// ---------------------------------------------------------------------------

@id("security.block-trajectory-injection-divergence")
@name("Block multi-turn injection the current turn hides")
@description("Blocks process_prompt and process_response when threaded state is in use, injection_deep_context_score >= 60, and injection_pulse_score < 40 — the conversation trajectory is an injection even though this single message is not.")
@severity("critical")
@tags("category:security,threat:injection,detection:ml,surface:process-prompt,surface:process-response,scope:multi-turn,owasp:llm01,mitre:atlas-t0051")
@reject_message("Blocked: this conversation is a progressive prompt-injection attempt. No single message crossed the line; the sequence did.")
forbid (
    principal,
    action in [Guardrails::Action::"process_prompt", Guardrails::Action::"process_response"],
    resource
)
when {
    context has multi_turn_detection && context.multi_turn_detection == true &&
    context has injection_deep_context_score && context.injection_deep_context_score >= 60 &&
    context has injection_pulse_score && context.injection_pulse_score < 40
};

@id("security.block-trajectory-jailbreak-divergence")
@name("Block multi-turn jailbreak the current turn hides")
@description("Blocks process_prompt and process_response when threaded state is in use, jailbreak_deep_context_score >= 60, and jailbreak_pulse_score < 40 — the conversation trajectory is a jailbreak even though this single message is not.")
@severity("critical")
@tags("category:security,threat:jailbreak,detection:ml,surface:process-prompt,surface:process-response,scope:multi-turn,owasp:llm02,mitre:atlas-t0054")
@reject_message("Blocked: this conversation is a progressive jailbreak. No single message crossed the line; the sequence did.")
forbid (
    principal,
    action in [Guardrails::Action::"process_prompt", Guardrails::Action::"process_response"],
    resource
)
when {
    context has multi_turn_detection && context.multi_turn_detection == true &&
    context has jailbreak_deep_context_score && context.jailbreak_deep_context_score >= 60 &&
    context has jailbreak_pulse_score && context.jailbreak_pulse_score < 40
};

// ---------------------------------------------------------------------------
// Section 2: Safety net — blatant trajectory, regardless of the pulse score
// ---------------------------------------------------------------------------
//
// Section 1 deliberately does NOT fire once pulse catches up (>= 40), because
// at that point the platform's default single-turn rules are the right owner
// of the decision. But those defaults only trip at injection_score >= 86 /
// jailbreak_score >= 81. This rule covers the band in between, where the
// trajectory is decisive but neither default threshold is met yet.

@id("security.block-trajectory-injection-high")
@name("Block high-confidence multi-turn injection")
@description("Blocks process_prompt and process_response when threaded state is in use and injection_deep_context_score >= 75.")
@severity("high")
@tags("category:security,threat:injection,detection:ml,surface:process-prompt,surface:process-response,scope:multi-turn,owasp:llm01")
@reject_message("Blocked: the deep-context model scored this conversation as a prompt-injection attempt with high confidence.")
forbid (
    principal,
    action in [Guardrails::Action::"process_prompt", Guardrails::Action::"process_response"],
    resource
)
when {
    context has multi_turn_detection && context.multi_turn_detection == true &&
    context has injection_deep_context_score && context.injection_deep_context_score >= 75
};

@id("security.block-trajectory-jailbreak-high")
@name("Block high-confidence multi-turn jailbreak")
@description("Blocks process_prompt and process_response when threaded state is in use and jailbreak_deep_context_score >= 75.")
@severity("high")
@tags("category:security,threat:jailbreak,detection:ml,surface:process-prompt,surface:process-response,scope:multi-turn,owasp:llm02")
@reject_message("Blocked: the deep-context model scored this conversation as a jailbreak attempt with high confidence.")
forbid (
    principal,
    action in [Guardrails::Action::"process_prompt", Guardrails::Action::"process_response"],
    resource
)
when {
    context has multi_turn_detection && context.multi_turn_detection == true &&
    context has jailbreak_deep_context_score && context.jailbreak_deep_context_score >= 75
};
